from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from typing import Optional

import structlog
import pandas as pd

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import AIEnrichment, EvidenceBundle, enrich_with_ai
from app.analytics.fundamental import load_fundamental_snapshot
from app.analytics.integrity import run_integrity_check
from app.analytics.technical import compute_technical_snapshot
from app.api.schemas import (
    DividendPointResponse,
    DividendSustainabilityResponse,
    FeasibilityCheckResponse,
    FundamentalSnapshotResponse,
    IntegrityReportResponse,
    MetricConflictResponse,
    PeerComparisonResponse,
    PeerFundamentalSnapshot,
    PriceBarResponse,
    PriceHistoryResponse,
    RecommendationResponse,
    FactorScoresResponse,
    StockOverviewResponse,
    TechnicalSnapshotResponse,
    TradeFeasibilityRequest,
    TradeFeasibilityResponse,
    InstrumentResponse,
)
from app.core.exceptions import DataNotFoundError
from app.db.models import Instrument, PriceBar
from app.db.session import get_db
from app.core.config import get_settings
from app.decisions.engine import (
    DecisionConfig,
    PortfolioContext,
    run_decision_engine,
)
from app.analytics.dividend_loader import load_dividend_analysis
from app.decisions.feasibility import check_trade_feasibility
from app.domain.instruments import resolve_instrument
from app.domain.investment_policy import get_or_create_default as get_policy
from app.analytics.gap_detector import detect_data_gaps
from app.ingestion.ohlcv import check_data_staleness, ingest_ohlcv
from app.ingestion.provider_fallback import ingest_with_fallback
from app.providers.registry import get_provider_registry

log = structlog.get_logger(__name__)

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
        integrity_status=fund_snap.integrity_status,
        integrity_blocked=fund_snap.integrity_blocked,
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

    # Load IPS dari DB — bukan hardcode
    policy = await get_policy(db)
    await db.commit()

    portfolio = PortfolioContext(
        owned=False,
        available_cash=999_999_999,  # UI akan override dengan data nyata
        max_position_weight=float(policy.max_position_weight),
        max_sector_weight=float(policy.max_sector_weight),
    )
    config = DecisionConfig(
        mode=policy.mode,
        buy_score_threshold=float(policy.buy_score_threshold),
        min_core_coverage=float(policy.min_core_coverage),
        max_staleness_days=policy.max_staleness_days,
        horizon=policy.horizon,
    )

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

    # AI enrichment — gagal graceful jika API key tidak ada
    settings = get_settings()
    sma_trend = "UNKNOWN"
    if not df.empty and tech.sma_20 and tech.sma_50:
        if tech.sma_20 > tech.sma_50:
            sma_trend = "BULLISH"
        elif tech.sma_20 < tech.sma_50:
            sma_trend = "BEARISH"
        else:
            sma_trend = "NEUTRAL"

    # Hitung peer medians dari DB (best-effort, tidak blokir analisis)
    _peer_pe: Optional[float] = None
    _peer_pb: Optional[float] = None
    _peer_roe: Optional[float] = None
    _peer_count: int = 0
    try:
        from statistics import median as _median
        _peer_result = await db.execute(
            select(Instrument).where(
                Instrument.sector == instrument.sector,
                Instrument.exchange == instrument.exchange,
                Instrument.id != instrument.id,
                Instrument.status == "active",
            ).limit(10)
        )
        _peer_instruments = list(_peer_result.scalars().all())
        if _peer_instruments:
            import asyncio as _asyncio
            _peer_snaps = await _asyncio.gather(*[
                load_fundamental_snapshot(db, p, today)
                for p in _peer_instruments
            ])
            _pe_vals = [s.pe_ratio for s in _peer_snaps if s.pe_ratio and s.pe_ratio > 0]
            _pb_vals = [s.pb_ratio for s in _peer_snaps if s.pb_ratio and s.pb_ratio > 0]
            _roe_vals = [s.roe for s in _peer_snaps if s.roe is not None]
            _peer_pe = _median(_pe_vals) if _pe_vals else None
            _peer_pb = _median(_pb_vals) if _pb_vals else None
            _peer_roe = _median(_roe_vals) if _roe_vals else None
            _peer_count = len(_peer_instruments)
    except Exception:
        log.warning("stocks.peer_context_failed", exc_info=True)

    bundle = EvidenceBundle(
        instrument_id=instrument.id,
        canonical_symbol=instrument.canonical_symbol,
        as_of=datetime.now(tz=timezone.utc),
        action=output.action.value,
        composite_score=output.composite_score,
        hard_gate_status=output.hard_gate_status.value,
        hard_gate_reason=output.hard_gate_reason,
        rsi_14=tech.rsi_14,
        macd=tech.macd,
        sma_trend=sma_trend,
        return_1d=tech.return_1d,
        return_20d=tech.return_20d,
        volume_ratio=tech.volume_ratio_20,
        pe_ratio=fund.pe_ratio,
        pb_ratio=fund.pb_ratio,
        roe=fund.roe,
        sector=fund.sector,
        is_bank=fund.sector == "Financials",
        factor_scores={
            "fundamental": output.factor_scores.fundamental,
            "valuation": output.factor_scores.valuation,
            "technical": output.factor_scores.technical,
            "macro_policy": output.factor_scores.macro_policy,
            "risk_quality": output.factor_scores.risk_quality,
        },
        bull_thesis_raw=output.bull_thesis,
        bear_case_raw=output.bear_case,
        data_gaps=output.data_gaps,
        provider=instrument.status,
        price_stale=staleness.get("stale", False),
        # R9: integrity context (BL-04)
        integrity_status=fund.integrity_status,
        integrity_conflicts_count=len(getattr(fund, "integrity_conflicts", []) or []),
        integrity_blocked_metrics=list(getattr(fund, "integrity_blocked", []) or []),
        # R9: peer context (R8)
        peer_pe_median=_peer_pe,
        peer_pb_median=_peer_pb,
        peer_roe_median=_peer_roe,
        peer_count=_peer_count,
    )

    enrichment: AIEnrichment = await enrich_with_ai(
        bundle,
        api_key=settings.anthropic_api_key if settings.anthropic_api_key else None,
        model=settings.anthropic_model,
        base_url=settings.anthropic_base_url if settings.anthropic_base_url else None,
    )

    # Merge AI poin ke thesis (AI hanya menambah, tidak mengganti)
    final_bull = output.bull_thesis + enrichment.enriched_bull_points
    final_bear = output.bear_case + enrichment.enriched_bear_points

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
        bull_thesis=final_bull,
        bear_case=final_bear,
        conditions_to_buy=output.conditions_to_buy,
        conditions_to_sell=output.conditions_to_sell,
        invalidation_triggers=output.invalidation_triggers,
        data_gaps=output.data_gaps,
        changed_from=output.changed_from,
        ai_enriched=not enrichment.skipped,
        ai_macro_context=enrichment.macro_context,
        ai_identified_risks=enrichment.identified_risks,
        ai_model=enrichment.model_used if not enrichment.skipped else None,
    )


@router.get("/{symbol}/integrity", response_model=IntegrityReportResponse)
async def get_integrity_report(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> IntegrityReportResponse:
    """
    Jalankan Financial Integrity Check terhadap semua FinancialFact instrument.
    Mengembalikan konflik cross-field, metrik yang diblokir, dan status keseluruhan.
    Tidak mengubah data — hanya laporan diagnostik.
    """
    from app.db.models import FinancialFact
    from sqlalchemy import select

    instrument = await _get_instrument_or_404(symbol, db)

    result = await db.execute(
        select(FinancialFact)
        .where(FinancialFact.instrument_id == instrument.id)
        .order_by(FinancialFact.period_end.desc(), FinancialFact.available_at.desc())
    )
    facts = list(result.scalars().all())

    report = run_integrity_check(instrument, facts)

    return IntegrityReportResponse(
        instrument_id=report.instrument_id,
        canonical_symbol=report.canonical_symbol,
        checked_at=report.checked_at,
        facts_checked=report.facts_checked,
        conflicts=[
            MetricConflictResponse(
                metric=c.metric,
                flag=c.flag.value,
                value=c.value,
                description=c.description,
                affected_downstream=c.affected_downstream,
            )
            for c in report.conflicts
        ],
        blocked_metrics=report.blocked_metrics,
        overall_status=report.overall_status,
    )


@router.post("/{symbol}/prices/refresh")
async def refresh_prices(
    symbol: str,
    days_back: int = Query(365, ge=1, le=1825, description="Berapa hari ke belakang untuk di-fetch"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Refresh harga dari provider (yfinance jika diaktifkan, mock jika tidak).
    Idempotent — bar yang sudah ada tidak di-insert ulang.
    Gunakan endpoint ini ketika data stale atau baru pertama kali setup.
    """
    instrument = await _get_instrument_or_404(symbol, db)

    end = date.today()
    start = end - timedelta(days=days_back)

    # Pilih provider berdasarkan exchange instrument
    registry = get_provider_registry()
    market = "IDX" if instrument.exchange in ("IDX", "BEI") else "US"
    provider = registry.get_primary(market)

    result = await ingest_ohlcv(db, instrument, provider, start, end)
    await db.commit()

    staleness = await check_data_staleness(db, instrument, end)

    return {
        "symbol": instrument.canonical_symbol,
        "provider": provider.name,
        "inserted": result.inserted,
        "skipped": result.skipped,
        "validation_errors": result.validation_errors[:10],  # max 10 baris error
        "stale_after_refresh": staleness.get("stale", True),
        "last_date": staleness.get("last_date"),
        "date_range": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "is_live_data": provider.name != "mock",
    }


@router.post("/{symbol}/data/refresh")
async def refresh_data_with_fallback(
    symbol: str,
    days_back: int = Query(365, ge=1, le=1825, description="Hari ke belakang untuk di-fetch"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Re-ingest OHLCV untuk satu instrumen menggunakan fallback chain (FREE-14).

    Berbeda dengan /prices/refresh yang hanya pakai primary provider,
    endpoint ini mencoba semua provider gratis secara berurutan hingga ada yang berhasil.
    Force=True: bar yang sudah ada diperbarui freshness_status-nya ke FRESH.
    Idempoten — bar yang identik tidak digandakan.
    """
    instrument = await _get_instrument_or_404(symbol, db)

    end = date.today()
    start = end - timedelta(days=days_back)
    market = "IDX" if instrument.exchange in ("IDX", "BEI") else "US"

    # Hitung gap sebelum refresh (opsional, untuk "before" stat)
    gap_before_result = await detect_data_gaps(db, threshold_pct=0, min_days_history=1, limit=1)
    gap_before = next(
        (r for r in gap_before_result.reports if r.instrument_id == str(instrument.id)),
        None,
    )

    fallback_result = await ingest_with_fallback(db, instrument, market, start, end, force=True)
    await db.commit()

    if fallback_result is None:
        return {
            "symbol": instrument.canonical_symbol,
            "status": "no_data",
            "provider_used": None,
            "fallback_used": False,
            "providers_tried": [],
            "bars_added": 0,
            "gap_pct_before": gap_before.gap_pct if gap_before else None,
            "gap_pct_after": gap_before.gap_pct if gap_before else None,
            "message": "Semua provider gratis tidak mengembalikan data untuk instrumen ini.",
        }

    # Hitung gap setelah refresh
    gap_after_result = await detect_data_gaps(db, threshold_pct=0, min_days_history=1, limit=1)
    gap_after = next(
        (r for r in gap_after_result.reports if r.instrument_id == str(instrument.id)),
        None,
    )

    return {
        "symbol": instrument.canonical_symbol,
        "status": "ok",
        "provider_used": fallback_result.provider_used,
        "fallback_used": fallback_result.fallback_used,
        "providers_tried": fallback_result.providers_tried,
        "bars_added": fallback_result.ohlcv.inserted,
        "bars_skipped": fallback_result.ohlcv.skipped,
        "gap_pct_before": gap_before.gap_pct if gap_before else None,
        "gap_pct_after": gap_after.gap_pct if gap_after else None,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
    }


@router.get("/{symbol}/peers", response_model=PeerComparisonResponse)
async def get_peers(
    symbol: str,
    limit: int = Query(10, ge=2, le=20, description="Jumlah peer maksimal (tidak termasuk subject)"),
    db: AsyncSession = Depends(get_db),
) -> PeerComparisonResponse:
    """
    Perbandingan fundamental lintas peer di sektor yang sama.
    Sumber data: FinancialFact di DB (tidak perlu API call).
    Peer diambil berdasarkan sektor + exchange yang sama, diurutkan berdasarkan market_cap DESC.
    """
    from sqlalchemy import select as sa_select
    from statistics import median

    instrument = await _get_instrument_or_404(symbol, db)
    today = date.today()

    if not instrument.sector:
        raise DataNotFoundError(f"Sektor {symbol} tidak diketahui — tidak bisa mencari peer.")

    # Ambil instrumen se-sektor dan se-exchange (max limit+1 termasuk subject)
    peer_result = await db.execute(
        sa_select(Instrument).where(
            Instrument.sector == instrument.sector,
            Instrument.exchange == instrument.exchange,
            Instrument.status == "ACTIVE",
        ).limit(limit + 1)
    )
    peer_instruments = list(peer_result.scalars().all())

    # Pastikan subject ada di daftar (mungkin sudah, mungkin tidak)
    peer_ids = {p.id for p in peer_instruments}
    if instrument.id not in peer_ids:
        peer_instruments.insert(0, instrument)

    # Load fundamental snapshot untuk setiap peer (paralel via gather)
    import asyncio
    snapshots = await asyncio.gather(*[
        load_fundamental_snapshot(db, p, today)
        for p in peer_instruments
    ])

    # Bangun response
    peers_resp: list[PeerFundamentalSnapshot] = []
    for inst, snap in zip(peer_instruments, snapshots):
        peers_resp.append(PeerFundamentalSnapshot(
            canonical_symbol=inst.canonical_symbol,
            company_name=inst.company_name,
            sector=inst.sector,
            pe_ratio=snap.pe_ratio,
            pb_ratio=snap.pb_ratio,
            roe=snap.roe,
            eps=snap.eps,
            gross_margin=snap.gross_margin,
            net_margin=getattr(snap, "net_margin", None),
            revenue=snap.revenue,
            net_income=snap.net_income,
            market_cap=snap.market_cap,
            dividend_yield=snap.dividend_yield,
            debt_to_equity=snap.debt_to_equity,
            nim=snap.nim,
            npl_gross=snap.npl_gross,
            car=snap.car,
            data_freshness=snap.data_freshness,
            period_end=snap.period_end,
            is_subject=(inst.id == instrument.id),
        ))

    # Hitung median metrik kunci (hanya dari nilai yang ada)
    pe_vals = [p.pe_ratio for p in peers_resp if p.pe_ratio is not None and p.pe_ratio > 0]
    pb_vals = [p.pb_ratio for p in peers_resp if p.pb_ratio is not None and p.pb_ratio > 0]
    roe_vals = [p.roe for p in peers_resp if p.roe is not None]

    return PeerComparisonResponse(
        subject_symbol=instrument.canonical_symbol,
        sector=instrument.sector,
        peers=peers_resp,
        peer_count=len(peers_resp),
        median_pe=median(pe_vals) if pe_vals else None,
        median_pb=median(pb_vals) if pb_vals else None,
        median_roe=median(roe_vals) if roe_vals else None,
        source="db",
        as_of=datetime.now(tz=timezone.utc),
    )


@router.post("/{symbol}/fundamentals/refresh")
async def refresh_fundamentals(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ambil ulang data fundamental dari provider (Sectors API jika aktif, yfinance jika tidak).
    Idempotent — fact yang sudah ada tidak di-insert ulang (upsert by unique constraint).
    """
    from app.ingestion.fundamentals import ingest_fundamentals

    instrument = await _get_instrument_or_404(symbol, db)
    market = "IDX" if instrument.exchange in ("IDX", "BEI") else "US"
    registry = get_provider_registry()
    provider = registry.get_fundamental_provider(market)

    inserted, skipped = await ingest_fundamentals(db, instrument, provider)
    await db.commit()

    return {
        "symbol": instrument.canonical_symbol,
        "provider": provider.name,
        "inserted": inserted,
        "skipped": skipped,
        "is_live_data": provider.name != "mock",
    }


@router.post("/{symbol}/feasibility", response_model=TradeFeasibilityResponse)
async def check_feasibility(
    symbol: str,
    body: TradeFeasibilityRequest,
    db: AsyncSession = Depends(get_db),
) -> TradeFeasibilityResponse:
    """
    R10: Trade Feasibility Engine.

    Hitung apakah trade potensial realistis secara pasar berdasarkan:
    - Lot size (IDX: 100 saham/lot; US: 1 saham)
    - Kecukupan modal untuk 1 lot
    - Batas posisi dari IPS (max_position_weight)
    - ADV liquidity check (jika data tersedia)
    - Estimasi spread cost

    TIDAK ADA eksekusi order — hanya analisis untuk keputusan manusia.
    """
    instrument = await _get_instrument_or_404(symbol, db)

    # Harga terakhir
    last_bar_result = await db.execute(
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument.id)
        .order_by(PriceBar.session_date.desc())
        .limit(1)
    )
    last_bar = last_bar_result.scalar_one_or_none()
    if not last_bar:
        from app.core.exceptions import DataNotFoundError
        raise DataNotFoundError(f"Tidak ada data harga untuk {symbol}")

    last_price = float(last_bar.close)

    # ADV dari 20 bar terakhir
    bars_result = await db.execute(
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument.id)
        .order_by(PriceBar.session_date.desc())
        .limit(20)
    )
    bars = list(bars_result.scalars().all())
    adv_shares: Optional[float] = None
    volumes = [float(b.volume) for b in bars if b.volume is not None]
    if len(volumes) >= 5:
        adv_shares = sum(volumes) / len(volumes)

    # IPS dari DB
    policy = await get_policy(db)
    await db.commit()

    exchange = "IDX" if instrument.exchange in ("IDX", "BEI") else "US"

    result = check_trade_feasibility(
        exchange=exchange,
        last_price=last_price,
        available_cash=body.available_cash,
        portfolio_total_value=body.portfolio_total_value,
        portfolio_weight_current=body.portfolio_weight_current,
        max_position_weight=float(policy.max_position_weight),
        adv_shares=adv_shares,
        desired_lots=body.desired_lots,
    )

    return TradeFeasibilityResponse(
        status=result.status.value,
        checks=[
            FeasibilityCheckResponse(
                name=c.name,
                passed=c.passed,
                is_hard_block=c.is_hard_block,
                message=c.message,
                value=c.value,
                threshold=c.threshold,
            )
            for c in result.checks
        ],
        lot_size=result.lot_size,
        min_lots=result.min_lots,
        min_cost_estimate=result.min_cost_estimate,
        suggested_lots=result.suggested_lots,
        suggested_cost=result.suggested_cost,
        adv_ratio=result.adv_ratio,
        spread_cost_pct=result.spread_cost_pct,
        warnings=result.warnings,
        blockers=result.blockers,
    )


@router.get("/{symbol}/dividend", response_model=DividendSustainabilityResponse)
async def get_dividend_analysis(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> DividendSustainabilityResponse:
    """
    R11: Dividend sustainability analysis.

    Menghitung apakah dividen berkelanjutan berdasarkan:
    - Payout ratio (DPS/EPS)
    - FCF coverage (DPS/FCF per saham)
    - Tren dividen 3 tahun terakhir
    - Real yield (dividend yield - inflasi terkini)
    - Dividend Growth Rate 3 tahun (CAGR)

    Data dari FinancialFact + MacroObservation — tidak ada angka LLM.
    """
    instrument = await _get_instrument_or_404(symbol, db)
    today = date.today()

    report = await load_dividend_analysis(db, instrument, today)

    return DividendSustainabilityResponse(
        instrument_id=report.instrument_id,
        as_of=report.as_of,
        rating=report.rating.value,
        trend=report.trend.value,
        latest_dps=report.latest_dps,
        latest_yield=report.latest_yield,
        payout_ratio=report.payout_ratio,
        fcf_payout_ratio=report.fcf_payout_ratio,
        dgr_3y=report.dgr_3y,
        inflation_rate=report.inflation_rate,
        real_yield=report.real_yield,
        history=[
            DividendPointResponse(
                year=p.year,
                dps=p.dps,
                eps=p.eps,
                fcf_per_share=p.fcf_per_share,
                payout_ratio=p.payout_ratio,
                fcf_payout_ratio=p.fcf_payout_ratio,
            )
            for p in report.history
        ],
        notes=report.notes,
        data_gaps=report.data_gaps,
    )
