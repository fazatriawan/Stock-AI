"""
Screener route — Phase D.

GET /screener  → Filter saham IDX/US berdasarkan fundamental + teknikal + sinyal engine.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.fundamental import load_fundamental_snapshot
from app.analytics.technical import TechnicalSnapshot, compute_technical_snapshot
from app.analytics.multibagger import MultibaggerInput, MultibaggerTier, score_multibagger
from app.api.schemas import (
    ScreenerResultResponse,
    ScreenerListResponse,
    ScoreComponentResponse,
    ReverseScenarioResponse,
    MultibaggerScoreResponse,
    MultibaggerResultResponse,
    MultibaggerListResponse,
)
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


# ---------------------------------------------------------------------------
# R15: Multibagger Screener
# ---------------------------------------------------------------------------

_TIER_ORDER = {
    MultibaggerTier.STRONG: 0,
    MultibaggerTier.MODERATE: 1,
    MultibaggerTier.WEAK: 2,
    MultibaggerTier.NOT_QUALIFIED: 3,
    MultibaggerTier.INSUFFICIENT: 4,
}


@router.get("/multibagger", response_model=MultibaggerListResponse)
async def screen_multibagger(
    sector: Optional[str] = Query(None, description="Filter sektor"),
    exchange: Optional[str] = Query(None, description="IDX atau NASDAQ/NYSE"),
    min_tier: str = Query("MODERATE", description="Tier minimum: STRONG, MODERATE, WEAK"),
    min_score: Optional[float] = Query(None, description="Skor minimum 0-100"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> MultibaggerListResponse:
    """
    Multibagger Screener — identifikasi saham kandidat pertumbuhan multi-tahun.

    Scoring (0–100) berbasis 4 dimensi:
    - Growth (25): revenue & EPS growth, akselerasi
    - Profitability (25): ROE, net margin, gross margin
    - Balance Sheet (25): DER, current ratio, FCF yield
    - Valuation (25): PE absolut & vs peer, PB

    Tier: STRONG (≥70), MODERATE (50–69), WEAK (30–49), NOT_QUALIFIED (<30).
    """
    today = date.today()

    # Validasi min_tier
    try:
        tier_filter = MultibaggerTier(min_tier.upper())
    except ValueError:
        tier_filter = MultibaggerTier.MODERATE

    tier_cutoff = _TIER_ORDER[tier_filter]

    # Ambil instrumen aktif
    query = select(Instrument).where(Instrument.status == "ACTIVE")
    if sector:
        query = query.where(Instrument.sector == sector)
    if exchange:
        query = query.where(Instrument.exchange == exchange)
    query = query.limit(_MAX_INSTRUMENTS)

    result = await db.execute(query)
    instruments = result.scalars().all()

    results: list[MultibaggerResultResponse] = []

    for instr in instruments:
        fund = await load_fundamental_snapshot(db, instr, today)

        # Bangun MultibaggerInput dari FundamentalSnapshot
        inp = MultibaggerInput(
            instrument_id=instr.id,
            symbol=instr.canonical_symbol,
            exchange=instr.exchange,
            sector=instr.sector,
            pe_ratio=fund.pe_ratio,
            pb_ratio=fund.pb_ratio,
            roe=fund.roe,
            net_margin=getattr(fund, "net_margin", None),
            gross_margin=fund.gross_margin,
            revenue_growth_1y=getattr(fund, "revenue_growth_1y", None),
            revenue_growth_3y=getattr(fund, "revenue_growth_3y", None),
            eps_growth_1y=getattr(fund, "eps_growth_1y", None),
            eps_growth_3y=getattr(fund, "eps_growth_3y", None),
            debt_to_equity=fund.debt_to_equity,
            current_ratio=getattr(fund, "current_ratio", None),
            fcf_yield=getattr(fund, "fcf_yield", None),
            fcf_margin=getattr(fund, "fcf_margin", None),
            price_vs_52w_high=None,
            relative_strength_1y=None,
            peer_pe_median=None,
            peer_roe_median=None,
        )

        mb_score = score_multibagger(inp)

        # Filter berdasarkan tier
        if _TIER_ORDER.get(mb_score.tier, 99) > tier_cutoff:
            continue

        # Filter berdasarkan skor minimum
        if min_score is not None and mb_score.total_score < min_score:
            continue

        # Ambil harga terkini
        df = await _load_price_df(instr.id, db)
        current_price = float(df["close"].iloc[-1]) if not df.empty else None

        results.append(MultibaggerResultResponse(
            instrument_id=instr.id,
            canonical_symbol=instr.canonical_symbol,
            company_name=instr.company_name,
            sector=instr.sector,
            exchange=instr.exchange,
            current_price=current_price,
            score=MultibaggerScoreResponse(
                instrument_id=instr.id,
                symbol=instr.canonical_symbol,
                tier=mb_score.tier.value,
                total_score=mb_score.total_score,
                components=[
                    ScoreComponentResponse(
                        name=c.name,
                        score=c.score,
                        max_score=c.max_score,
                        notes=c.notes,
                    )
                    for c in mb_score.components
                ],
                strengths=mb_score.strengths,
                concerns=mb_score.concerns,
                data_completeness=mb_score.data_completeness,
                pipelines_matched=mb_score.pipelines_matched,
                reverse_scenarios=[
                    ReverseScenarioResponse(
                        target_multiple=s.target_multiple,
                        horizon_years=s.horizon_years,
                        required_eps_cagr_constant_pe_pct=s.required_eps_cagr_constant_pe_pct,
                        required_eps_cagr_rerating_pct=s.required_eps_cagr_rerating_pct,
                        assumed_annual_dilution_pct=s.assumed_annual_dilution_pct,
                        downside_risk_note=s.downside_risk_note,
                    )
                    for s in mb_score.reverse_scenarios
                ],
            ),
            pe_ratio=fund.pe_ratio,
            roe=fund.roe,
            net_margin=getattr(fund, "net_margin", None),
            revenue_growth_1y=getattr(fund, "revenue_growth_1y", None),
            debt_to_equity=fund.debt_to_equity,
            data_freshness=fund.data_freshness,
        ))

    # Sort: tier dulu, lalu score desc
    results.sort(key=lambda r: (_TIER_ORDER.get(MultibaggerTier(r.score.tier), 99), -r.score.total_score))
    results = results[:limit]

    log.info("multibagger.results", total=len(results), min_tier=min_tier)

    return MultibaggerListResponse(
        results=results,
        total=len(results),
        min_tier=min_tier,
        as_of=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Sector Rotation (Fitur Baru)
# ---------------------------------------------------------------------------

from app.analytics.sector_rotation import compute_sector_rotation  # noqa: E402


@router.get("/sectors/rotation", response_model=dict)
async def get_sector_rotation(
    lookback_days: int = Query(90, ge=30, le=365),
    exchange: str = Query("IDX"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Analisis rotasi sektor berdasarkan momentum return rata-rata saham per sektor.

    Berguna untuk melihat sektor mana yang sedang diakumulasi vs distribusi oleh pasar.
    """
    end   = date.today()
    start = end - timedelta(days=lookback_days)

    # Ambil semua instrumen aktif di exchange yang diminta
    instrs_result = await db.execute(
        select(Instrument)
        .where(Instrument.status == "ACTIVE", Instrument.exchange == exchange.upper(), Instrument.sector.isnot(None))
    )
    instrs = instrs_result.scalars().all()

    if not instrs:
        return {
            "rotation_detected": False,
            "rotation_note": f"Tidak ada instrumen aktif di exchange {exchange}",
            "top_sectors": [], "bottom_sectors": [], "all_sectors": [], "as_of": None,
        }

    # Kelompokkan per sektor, hitung rata-rata harga penutupan per tanggal
    sector_data: dict[str, dict] = {}
    for instr in instrs:
        sec = instr.sector
        if not sec:
            continue
        if sec not in sector_data:
            sector_data[sec] = {"instrument_id": instr.id, "ids": []}
        sector_data[sec]["ids"].append(instr.id)

    import pandas as pd
    sector_prices: dict[str, pd.Series] = {}

    for sec, info in sector_data.items():
        ids = info["ids"]
        bars_result = await db.execute(
            select(PriceBar.session_date, func.avg(PriceBar.close).label("avg_close"))
            .where(PriceBar.instrument_id.in_(ids), PriceBar.session_date.between(start, end))
            .group_by(PriceBar.session_date)
            .order_by(PriceBar.session_date.asc())
        )
        rows = bars_result.all()
        if rows:
            s = pd.Series({r[0]: float(r[1]) for r in rows})
            sector_prices[sec] = s

    report = compute_sector_rotation(sector_prices)
    return {
        "rotation_detected": report.rotation_detected,
        "rotation_note": report.rotation_note,
        "as_of": report.as_of,
        "top_sectors": [
            {
                "sector": s.sector, "return_1w": s.return_1w, "return_1m": s.return_1m,
                "return_3m": s.return_3m, "momentum_score": s.momentum_score, "signal": s.signal,
            }
            for s in report.top_sectors
        ],
        "bottom_sectors": [
            {
                "sector": s.sector, "return_1w": s.return_1w, "return_1m": s.return_1m,
                "return_3m": s.return_3m, "momentum_score": s.momentum_score, "signal": s.signal,
            }
            for s in report.bottom_sectors
        ],
        "all_sectors": [
            {
                "sector": s.sector, "return_1w": s.return_1w, "return_1m": s.return_1m,
                "return_3m": s.return_3m, "momentum_score": s.momentum_score, "signal": s.signal,
            }
            for s in report.all_sectors
        ],
    }
