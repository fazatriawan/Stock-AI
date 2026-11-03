"""
Screener route — Phase D.

GET /screener  → Filter saham IDX/US berdasarkan fundamental + teknikal + sinyal engine.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.fundamental import load_fundamental_snapshot
from app.analytics.technical import TechnicalSnapshot, compute_technical_snapshot
from app.api.schemas import ScreenerResultResponse, ScreenerListResponse
from app.db.models import Instrument, PriceBar
from app.db.session import get_db
from app.decisions.engine import (
    DecisionConfig,
    PortfolioContext,
    run_decision_engine,
)

import pandas as pd

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/screener", tags=["screener"])

_PRICE_DAYS = 300
_MAX_INSTRUMENTS = 200  # batasi untuk performa


async def _load_price_df(instrument_id: str, db: AsyncSession) -> pd.DataFrame:
    end = date.today()
    start = end - timedelta(days=_PRICE_DAYS)
    result = await db.execute(
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument_id,
               PriceBar.session_date.between(start, end))
        .order_by(PriceBar.session_date.asc())
    )
    bars = result.scalars().all()
    if not bars:
        return pd.DataFrame()
    return pd.DataFrame([{
        "session_date": b.session_date,
        "close": float(b.close),
        "high": float(b.high) if b.high else float(b.close),
        "low": float(b.low) if b.low else float(b.close),
        "open": float(b.open) if b.open else float(b.close),
        "volume": b.volume or 0,
    } for b in bars])


@router.get("", response_model=ScreenerListResponse)
async def screen_stocks(
    sector: Optional[str] = Query(None, description="Filter sektor: Finance, Consumer, Telecoms, dll"),
    exchange: Optional[str] = Query(None, description="IDX atau NASDAQ/NYSE"),
    min_roe: Optional[float] = Query(None, description="ROE minimum (0.10 = 10%)"),
    max_pe: Optional[float] = Query(None, description="P/E maksimum"),
    min_pe: Optional[float] = Query(None, description="P/E minimum (filter buang negatif)"),
    min_composite: Optional[float] = Query(None, description="Skor komposit minimum (0-100)"),
    action: Optional[str] = Query(None, description="Filter action: BUY,WAIT,HOLD,dll"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ScreenerListResponse:
    """
    Screener saham berdasarkan kriteria fundamental dan teknikal.

    Semua filter bersifat opsional dan dapat dikombinasikan.
    Hasil diurutkan berdasarkan skor komposit (tinggi ke rendah).
    """
    today = date.today()
    config = DecisionConfig()
    portfolio_ctx = PortfolioContext(owned=False, available_cash=999_999_999)

    # Ambil instrumen
    query = select(Instrument).where(Instrument.status == "ACTIVE")
    if sector:
        query = query.where(Instrument.sector == sector)
    if exchange:
        query = query.where(Instrument.exchange == exchange)
    query = query.limit(_MAX_INSTRUMENTS)

    result = await db.execute(query)
    instruments = result.scalars().all()

    results: list[ScreenerResultResponse] = []

    for instr in instruments:
        fund = await load_fundamental_snapshot(db, instr, today)

        # Fundamental filters
        if min_roe is not None and (fund.roe is None or fund.roe < min_roe):
            continue
        if max_pe is not None and (fund.pe_ratio is None or fund.pe_ratio > max_pe):
            continue
        if min_pe is not None and (fund.pe_ratio is None or fund.pe_ratio < min_pe):
            continue

        df = await _load_price_df(instr.id, db)
        tech = (
            compute_technical_snapshot(instr.id, df, today)
            if not df.empty
            else TechnicalSnapshot(instrument_id=instr.id, as_of=today)
        )

        output = run_decision_engine(
            instrument_id=instr.id,
            as_of=today,
            technical=tech,
            fundamental=fund,
            portfolio=portfolio_ctx,
            config=config,
            stale_price=(df.empty),
        )

        # Action filter
        if action and output.action.value != action:
            continue

        # Min composite filter
        if min_composite is not None and output.composite_score < min_composite:
            continue

        current_price = float(df["close"].iloc[-1]) if not df.empty else None

        results.append(ScreenerResultResponse(
            instrument_id=instr.id,
            canonical_symbol=instr.canonical_symbol,
            company_name=instr.company_name,
            sector=instr.sector,
            exchange=instr.exchange,
            current_price=current_price,
            action=output.action.value,
            composite_score=round(output.composite_score, 1),
            evidence_confidence=output.evidence_confidence,
            pe_ratio=fund.pe_ratio,
            pb_ratio=fund.pb_ratio,
            roe=fund.roe,
            dividend_yield=fund.dividend_yield,
            rsi_14=tech.rsi_14,
            above_sma_200=tech.above_sma_200,
            return_20d=tech.return_20d,
            data_freshness=fund.data_freshness,
        ))

    # Sort composite score desc
    results.sort(key=lambda r: -r.composite_score)
    results = results[:limit]

    log.info("screener.results", total=len(results), sector=sector, action=action)

    return ScreenerListResponse(
        results=results,
        total=len(results),
        filters_applied={
            "sector": sector,
            "exchange": exchange,
            "min_roe": min_roe,
            "max_pe": max_pe,
            "min_pe": min_pe,
            "min_composite": min_composite,
            "action": action,
        },
        as_of=datetime.now(tz=timezone.utc),
    )
