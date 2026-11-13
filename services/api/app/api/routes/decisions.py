"""
Decisions route — Phase D.

GET /decisions  → Jalankan decision engine untuk semua posisi portfolio + watchlist.
Deterministik: engine tidak memanggil LLM, LLM hanya menambah narasi opsional.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.fundamental import load_fundamental_snapshot
from app.analytics.technical import TechnicalSnapshot, compute_technical_snapshot
from app.api.schemas import DecisionListResponse, DecisionSummaryResponse
from app.db.models import Instrument, PriceBar, Trade, WatchlistItem
from app.db.session import get_db
from app.decisions.engine import (
    DecisionConfig,
    PortfolioContext,
    run_decision_engine,
)
from app.ingestion.ohlcv import check_data_staleness
from app.portfolio.calculator import compute_positions, enrich_positions_with_prices
from app.portfolio.seeder import get_or_create_default_portfolio

import pandas as pd

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/decisions", tags=["decisions"])

_PRICE_DAYS = 300


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


@router.get("", response_model=DecisionListResponse)
async def list_decisions(
    action: str | None = Query(None, description="Filter: BUY,ADD_CANDIDATE,HOLD,TRIM_CANDIDATE,SELL,WAIT,INSUFFICIENT_DATA"),
    include_watchlist: bool = Query(True, description="Sertakan watchlist (owned=False)"),
    db: AsyncSession = Depends(get_db),
) -> DecisionListResponse:
    """
    Jalankan decision engine pada:
    1. Semua posisi aktif portofolio (owned=True)
    2. Semua item watchlist (owned=False, jika include_watchlist=True)

    Action dihasilkan deterministik dari data fundamental + teknikal.
    Tidak ada LLM dalam route ini.
    """
    today = date.today()
    config = DecisionConfig()
    results: list[DecisionSummaryResponse] = []

    # --- 1. Portfolio positions ---
    portfolio = await get_or_create_default_portfolio(db)
    trades_result = await db.execute(
        select(Trade).where(Trade.portfolio_id == portfolio.id)
    )
    trades = trades_result.scalars().all()
    positions = compute_positions(trades)

    # Enrich positions dengan harga terkini agar portfolio_weight benar
    if positions:
        prices_map: dict[str, tuple[float, date]] = {}
        for iid in list(positions.keys()):
            bar_res = await db.execute(
                select(PriceBar)
                .where(PriceBar.instrument_id == iid)
                .order_by(PriceBar.session_date.desc())
                .limit(1)
            )
            bar = bar_res.scalar_one_or_none()
            if bar:
                prices_map[iid] = (float(bar.close), bar.session_date)
        enrich_positions_with_prices(positions, prices_map)

    # Enrich dengan info instrumen
    if positions:
        instr_result = await db.execute(
            select(Instrument).where(Instrument.id.in_(list(positions.keys())))
        )
        instruments_map = {i.id: i for i in instr_result.scalars().all()}

        for iid, pos in positions.items():
            instr = instruments_map.get(iid)
            if not instr:
                continue

            df = await _load_price_df(iid, db)
            staleness = await check_data_staleness(db, instr, today)

            tech = (
                compute_technical_snapshot(iid, df, today)
                if not df.empty
                else TechnicalSnapshot(instrument_id=iid, as_of=today)
            )
            fund = await load_fundamental_snapshot(db, instr, today)

            sector_weight = 0.0
            if instr.sector:
                sector_weight = sum(
                    p.weight for p in positions.values()
                    if (instruments_map.get(p.instrument_id) or instr).sector == instr.sector
                )

            portfolio_ctx = PortfolioContext(
                owned=True,
                shares=pos.shares,
                cost_basis=pos.avg_cost,
                portfolio_weight=pos.weight,
                sector_weight=sector_weight,
                available_cash=0,
            )

            output = run_decision_engine(
                instrument_id=iid,
                as_of=today,
                technical=tech,
                fundamental=fund,
                portfolio=portfolio_ctx,
                config=config,
                stale_price=staleness.get("stale", False),
            )

            if action and output.action.value != action:
                continue

            current_price = None
            if not df.empty:
                current_price = float(df["close"].iloc[-1])

            results.append(DecisionSummaryResponse(
                instrument_id=iid,
                canonical_symbol=instr.canonical_symbol,
                company_name=instr.company_name,
                sector=instr.sector,
                action=output.action.value,
                urgency=output.urgency.value,
                composite_score=round(output.composite_score, 1),
                evidence_confidence=output.evidence_confidence,
                hard_gate_status=output.hard_gate_status.value,
                hard_gate_reason=output.hard_gate_reason,
                owned=True,
                portfolio_weight=round(pos.weight * 100, 1),
                current_price=current_price,
                bull_thesis=output.bull_thesis[:2],
                bear_case=output.bear_case[:2],
                data_gaps=output.data_gaps[:3],
                factor_scores={
                    "fundamental": round(output.factor_scores.fundamental, 1) if output.factor_scores.fundamental else None,
                    "valuation": round(output.factor_scores.valuation, 1) if output.factor_scores.valuation else None,
                    "technical": round(output.factor_scores.technical, 1) if output.factor_scores.technical else None,
                },
            ))

    # --- 2. Watchlist items ---
    if include_watchlist:
        wl_result = await db.execute(select(WatchlistItem))
        wl_items = wl_result.scalars().all()

        # Hindari duplikasi dengan posisi yang sudah diproses
        owned_instrument_ids = set(positions.keys())

        for item in wl_items:
            if item.instrument_id in owned_instrument_ids:
                continue

            instr_result = await db.execute(
                select(Instrument).where(Instrument.id == item.instrument_id)
            )
            instr = instr_result.scalar_one_or_none()
            if not instr:
                continue

            df = await _load_price_df(item.instrument_id, db)
            staleness = await check_data_staleness(db, instr, today)

            tech = (
                compute_technical_snapshot(item.instrument_id, df, today)
                if not df.empty
                else TechnicalSnapshot(instrument_id=item.instrument_id, as_of=today)
            )
            fund = await load_fundamental_snapshot(db, instr, today)

            portfolio_ctx = PortfolioContext(
                owned=False,
                available_cash=999_999_999,
            )

            output = run_decision_engine(
                instrument_id=item.instrument_id,
                as_of=today,
                technical=tech,
                fundamental=fund,
                portfolio=portfolio_ctx,
                config=config,
                stale_price=staleness.get("stale", False),
            )

            if action and output.action.value != action:
                continue

            current_price = None
            if not df.empty:
                current_price = float(df["close"].iloc[-1])

            results.append(DecisionSummaryResponse(
                instrument_id=item.instrument_id,
                canonical_symbol=instr.canonical_symbol,
                company_name=instr.company_name,
                sector=instr.sector,
                action=output.action.value,
                urgency=output.urgency.value,
                composite_score=round(output.composite_score, 1),
                evidence_confidence=output.evidence_confidence,
                hard_gate_status=output.hard_gate_status.value,
                hard_gate_reason=output.hard_gate_reason,
                owned=False,
                portfolio_weight=None,
                current_price=current_price,
                bull_thesis=output.bull_thesis[:2],
                bear_case=output.bear_case[:2],
                data_gaps=output.data_gaps[:3],
                factor_scores={
                    "fundamental": round(output.factor_scores.fundamental, 1) if output.factor_scores.fundamental else None,
                    "valuation": round(output.factor_scores.valuation, 1) if output.factor_scores.valuation else None,
                    "technical": round(output.factor_scores.technical, 1) if output.factor_scores.technical else None,
                },
            ))

    # Sort: urgency REVIEW_NOW dulu, lalu composite score desc
    urgency_order = {"REVIEW_NOW": 0, "NORMAL": 1}
    results.sort(key=lambda r: (urgency_order.get(r.urgency, 2), -r.composite_score))

    action_counts: dict[str, int] = {}
    for r in results:
        action_counts[r.action] = action_counts.get(r.action, 0) + 1

    log.info("decisions.list", total=len(results), action_filter=action)

    return DecisionListResponse(
        decisions=results,
        total=len(results),
        action_counts=action_counts,
        generated_at=datetime.now(tz=timezone.utc),
    )
