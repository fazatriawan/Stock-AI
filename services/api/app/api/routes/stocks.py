from datetime import date, datetime, timezone, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.fundamental import load_fundamental_snapshot
from app.analytics.technical import compute_technical_snapshot
from app.api.schemas import (
    FundamentalSnapshotResponse,
    PriceBarResponse,
    PriceHistoryResponse,
    RecommendationResponse,
    FactorScoresResponse,
    StockOverviewResponse,
    TechnicalSnapshotResponse,
    InstrumentResponse,
)
from app.core.exceptions import DataNotFoundError
from app.db.models import Instrument, PriceBar
from app.db.session import get_db
from app.decisions.engine import (
    DecisionConfig,
    PortfolioContext,
    run_decision_engine,
)
from app.domain.instruments import resolve_instrument
from app.ingestion.ohlcv import check_data_staleness

router = APIRouter(prefix="/stocks", tags=["stocks"])


async def _get_instrument_or_404(symbol: str, db: AsyncSession) -> Instrument:
    instrument = await resolve_instrument(db, symbol)
    if not instrument:
        raise DataNotFoundError(f"Instrument tidak ditemukan: {symbol}")
    return instrument


async def _load_price_df(
    instrument_id: str,
    db: AsyncSession,
    days: int = 300,
    end: date | None = None,
) -> pd.DataFrame:
    end = end or date.today()
    start = end - timedelta(days=days)
    result = await db.execute(
        select(PriceBar)
        .where(
            PriceBar.instrument_id == instrument_id,
            PriceBar.session_date.between(start, end),
        )
        .order_by(PriceBar.session_date.asc())
    )
    bars = result.scalars().all()
    if not bars:
        return pd.DataFrame()
    return pd.DataFrame([{
        "session_date": b.session_date,
        "open": float(b.open) if b.open else None,
        "high": float(b.high) if b.high else None,
        "low": float(b.low) if b.low else None,
        "close": float(b.close),
        "adj_close": float(b.adj_close) if b.adj_close else None,
        "volume": b.volume,
        "provider": b.provider,
        "is_adjusted": b.is_adjusted,
    } for b in bars])


@router.get("/{symbol}/prices", response_model=PriceHistoryResponse)
async def get_prices(
    symbol: str,
    range: str = Query("1y", description="1m, 3m, 6m, 1y, 2y, 5y"),
    adjusted: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> PriceHistoryResponse:
    """OHLCV historis untuk satu instrument."""
    instrument = await _get_instrument_or_404(symbol, db)

    range_days = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "2y": 730, "5y": 1825}.get(range, 365)
    end = date.today()
    start = end - timedelta(days=range_days)

    result = await db.execute(
        select(PriceBar)
        .where(
            PriceBar.instrument_id == instrument.id,
            PriceBar.session_date.between(start, end),
        )
        .order_by(PriceBar.session_date.asc())
    )
    bars = result.scalars().all()
    provider = bars[0].provider if bars else "unknown"

    return PriceHistoryResponse(
        instrument=InstrumentResponse.model_validate(instrument),
        bars=[PriceBarResponse.model_validate(b) for b in bars],
        count=len(bars),
        start=start,
        end=end,
        provider=provider,
        as_of=datetime.now(tz=timezone.utc),
    )


@router.get("/{symbol}/overview", response_model=StockOverviewResponse)
async def get_overview(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> StockOverviewResponse:
    """Snapshot lengkap: harga terbaru, technical, fundamental."""
    instrument = await _get_instrument_or_404(symbol, db)
    now = datetime.now(tz=timezone.utc)
    today = now.date()

    # Price
    price_result = await db.execute(
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument.id)
        .order_by(PriceBar.session_date.desc())
        .limit(1)
    )
    last_bar = price_result.scalar_one_or_none()
    staleness = await check_data_staleness(db, instrument, today)

    # Technical
    df = await _load_price_df(instrument.id, db, days=300)
    tech_snap = None
    if not df.empty:
        snap = compute_technical_snapshot(instrument.id, df, today)
        tech_snap = TechnicalSnapshotResponse(
            instrument_id=snap.instrument_id,
            as_of=snap.as_of,
            sma_20=snap.sma_20, sma_50=snap.sma_50, sma_200=snap.sma_200,
            ema_20=snap.ema_20, rsi_14=snap.rsi_14,
            macd=snap.macd, macd_signal=snap.macd_signal, macd_hist=snap.macd_hist,
            atr_14=snap.atr_14, realized_vol_20=snap.realized_vol_20,
            above_sma_200=snap.above_sma_200, golden_cross=snap.golden_cross,
            return_1d=snap.return_1d, return_5d=snap.return_5d,
            return_20d=snap.return_20d, high_52w=snap.high_52w,
            low_52w=snap.low_52w, percentile_52w=snap.percentile_52w,
            volume_ratio_20=snap.volume_ratio_20,
            bars_available=snap.bars_available,
            sufficient_data=snap.sufficient_data,
            missing_indicators=snap.missing_indicators,
        )

    # Fundamental
    fund_snap = await load_fundamental_snapshot(db, instrument, today)
    fund_resp = FundamentalSnapshotResponse(
        instrument_id=fund_snap.instrument_id,
        as_of=fund_snap.as_of,
        sector=fund_snap.sector,
        pe_ratio=fund_snap.pe_ratio, pb_ratio=fund_snap.pb_ratio,
        roe=fund_snap.roe, eps=fund_snap.eps,
        revenue=fund_snap.revenue, net_income=fund_snap.net_income,
        market_cap=fund_snap.market_cap, dividend_yield=fund_snap.dividend_yield,
        debt_to_equity=fund_snap.debt_to_equity,
        gross_margin=fund_snap.gross_margin, operating_margin=fund_snap.operating_margin,
        nim=fund_snap.nim, npl_gross=fund_snap.npl_gross, car=fund_snap.car,
        metrics_available=fund_snap.metrics_available,
        metrics_missing=fund_snap.metrics_missing,
        data_freshness=fund_snap.data_freshness,
        period_end=fund_snap.period_end,
    )

    return StockOverviewResponse(
        instrument=InstrumentResponse.model_validate(instrument),
        last_price=float(last_bar.close) if last_bar else None,
        last_price_date=last_bar.session_date if last_bar else None,
        price_provider=last_bar.provider if last_bar else None,
        price_stale=staleness.get("stale", True),
        technical=tech_snap,
        fundamental=fund_resp,
        as_of=now,
    )


@router.get("/{symbol}/analysis", response_model=RecommendationResponse)
async def get_analysis(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    """
    Analisis deterministik — BUY/HOLD/SELL/WAIT/INSUFFICIENT_DATA.
    LLM tidak terlibat dalam menentukan action ini.
    """
    instrument = await _get_instrument_or_404(symbol, db)
    today = date.today()

    # Load data
    df = await _load_price_df(instrument.id, db, days=300)
    staleness = await check_data_staleness(db, instrument, today)

    from app.analytics.technical import TechnicalSnapshot
    if not df.empty:
        tech = compute_technical_snapshot(instrument.id, df, today)
    else:
        tech = TechnicalSnapshot(as_of=today, instrument_id=instrument.id)

    fund = await load_fundamental_snapshot(db, instrument, today)

    portfolio = PortfolioContext(
        owned=False,
        available_cash=999_999_999,  # UI akan override dengan data nyata
    )
    config = DecisionConfig()

    output = run_decision_engine(
        instrument_id=instrument.id,
        as_of=today,
        technical=tech,
        fundamental=fund,
        portfolio=portfolio,
        config=config,
        stale_price=staleness.get("stale", False),
    )

    scores = FactorScoresResponse(
        fundamental=output.factor_scores.fundamental,
        valuation=output.factor_scores.valuation,
        technical=output.factor_scores.technical,
        macro_policy=output.factor_scores.macro_policy,
        risk_quality=output.factor_scores.risk_quality,
        events_news=output.factor_scores.events_news,
        ownership_flows=output.factor_scores.ownership_flows,
        composite=output.composite_score,
        coverage=output.factor_scores.coverage(),
    )

    return RecommendationResponse(
        instrument_id=instrument.id,
        canonical_symbol=instrument.canonical_symbol,
        as_of=datetime.now(tz=timezone.utc),
        action=output.action.value,
        urgency=output.urgency.value,
        horizon=output.horizon,
        hard_gate_status=output.hard_gate_status.value,
        hard_gate_reason=output.hard_gate_reason,
        factor_scores=scores,
        evidence_confidence=output.evidence_confidence,
        owned=output.owned,
        bull_thesis=output.bull_thesis,
        bear_case=output.bear_case,
        conditions_to_buy=output.conditions_to_buy,
        conditions_to_sell=output.conditions_to_sell,
        invalidation_triggers=output.invalidation_triggers,
        data_gaps=output.data_gaps,
        changed_from=output.changed_from,
    )
