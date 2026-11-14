from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.api.schemas import (
    BatchRefreshItemResult,
    BatchRefreshResponse,
    CSVImportResponse,
    ProviderSuccessResponse,
    ProviderSuccessRow,
    CoverageStatusResponse,
    DataGapsResponse,
    DataHealthResponse,
    DataProviderResponse,
    DataProvidersResponse,
    FreshnessBreakdown,
    GapReportRow,
    HealGapsResponse,
    InstrumentFreshnessResponse,
    MarkStaleResponse,
    ProviderHealthResponse,
    ProviderQuotaResponse,
    ProviderQuotaRow,
    RefreshStaleResponse,
    ResetQuotaResponse,
    StaleInstrumentRow,
    StaleInstrumentsResponse,
)
from app.db.session import get_db
from app.domain.instruments import resolve_instrument
from app.ingestion.provider_fallback import ingest_with_fallback
from app.providers.quota_tracker import get_quota_tracker
from app.providers.registry import get_provider_registry

router = APIRouter(prefix="/data", tags=["data"])
log = structlog.get_logger(__name__)


@router.get("/health", response_model=DataHealthResponse)
async def get_data_health() -> DataHealthResponse:
    """Status semua provider data: OK / DEGRADED / DOWN."""
    registry = get_provider_registry()
    health_list = registry.all_health()
    return DataHealthResponse(
        providers=[
            ProviderHealthResponse(
                provider=h.provider,
                status=h.status.value,
                last_success=h.last_success,
                last_error=h.last_error,
                latency_ms=h.latency_ms,
                notes=h.notes,
            )
            for h in health_list
        ],
        checked_at=datetime.now(tz=timezone.utc),
    )


@router.get("/providers", response_model=DataProvidersResponse)
async def get_data_providers() -> DataProvidersResponse:
    """
    Capability + health tiap provider yang terdaftar.
    Digunakan oleh Data Health UI di Settings.
    """
    registry = get_provider_registry()
    health_map = {h.provider: h for h in registry.all_health()}
    result: list[DataProviderResponse] = []

    for name, provider in registry._provider_by_name.items():
        try:
            cap = provider.capability()
        except Exception:
            log.warning("data_health.capability_failed", provider=name, exc_info=True)
            cap = None  # type: ignore[assignment]

        h = health_map.get(name)
        result.append(DataProviderResponse(
            provider=name,
            health_status=h.status.value if h else "UNKNOWN",
            license_status=cap.license_status.value if cap else "UNKNOWN",
            access_status=cap.access_status.value if cap else "UNKNOWN",
            cost=cap.cost if cap else "unknown",
            datasets=cap.datasets if cap else [],
            granularity=cap.granularity if cap else "unknown",
            freshness_policy=cap.freshness_policy if cap else "unknown",
            last_success=h.last_success if h else None,
            last_error=h.last_error if h else None,
            notes=cap.notes if cap else None,
        ))

    return DataProvidersResponse(
        providers=result,
        checked_at=datetime.now(tz=timezone.utc),
    )


@router.post("/import/csv", response_model=CSVImportResponse)
async def import_ohlcv_csv_endpoint(
    file: UploadFile = File(...),
    instrument_id: str = Form(...),
    provider: str = Form(default="csv_manual"),
    db=Depends(get_db),
) -> CSVImportResponse:
    """
    Import OHLCV dari file CSV.
    Form fields: instrument_id (wajib), provider (opsional, default csv_manual).
    CSV harus punya kolom: date, close (minimal). Kolom opsional: open, high, low, volume.
    """
    from app.ingestion.csv_ohlcv_importer import import_ohlcv_csv

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Hanya file .csv yang diterima")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB max
        raise HTTPException(status_code=413, detail="File terlalu besar — maksimum 10 MB")

    result = await import_ohlcv_csv(
        db=db,
        instrument_id=instrument_id,
        provider=provider,
        content=content,
        source_url=file.filename,
    )
    await db.commit()

    return CSVImportResponse(
        inserted=result.inserted,
        skipped_duplicate=result.skipped_duplicate,
        skipped_existing_source=result.skipped_existing_source,
        parse_errors=result.parse_errors,
        source_id=result.source_id,
    )


@router.get("/freshness/{instrument_id}", response_model=InstrumentFreshnessResponse)
async def get_instrument_freshness(
    instrument_id: str,
    db=Depends(get_db),
) -> InstrumentFreshnessResponse:
    """
    Ringkasan kualitas data harga untuk satu instrumen.
    Menghitung distribusi freshness_status dari price_bars.
    """
    from sqlalchemy import func, select
    from app.db.models import PriceBar

    # Distribusi per status
    rows = await db.execute(
        select(PriceBar.freshness_status, func.count().label("cnt"))
        .where(PriceBar.instrument_id == instrument_id)
        .group_by(PriceBar.freshness_status)
    )
    breakdown_raw = {r.freshness_status: r.cnt for r in rows}

    total = sum(breakdown_raw.values())
    fresh = breakdown_raw.get("FRESH", 0)
    stale = breakdown_raw.get("STALE", 0)
    other = total - fresh - stale

    # Tanggal bar terakhir dan tanggal FRESH terakhir
    last_bar = await db.scalar(
        select(func.max(PriceBar.session_date))
        .where(PriceBar.instrument_id == instrument_id)
    )
    last_fresh = await db.scalar(
        select(func.max(PriceBar.session_date))
        .where(
            PriceBar.instrument_id == instrument_id,
            PriceBar.freshness_status == "FRESH",
        )
    )

    quality_pct = round(fresh / total * 100, 1) if total > 0 else 0.0

    return InstrumentFreshnessResponse(
        instrument_id=instrument_id,
        total_bars=total,
        fresh_bars=fresh,
        stale_bars=stale,
        other_bars=other,
        data_quality_pct=quality_pct,
        last_fresh_date=last_fresh,
        last_bar_date=last_bar,
        breakdown=[
            FreshnessBreakdown(status=s, count=c)
            for s, c in sorted(breakdown_raw.items())
        ],
    )


@router.post("/mark-stale", response_model=MarkStaleResponse)
async def mark_stale_endpoint(
    instrument_id: Optional[str] = Query(default=None, description="Batasi ke satu instrumen (UUID). Kosong = semua."),
    db=Depends(get_db),
) -> MarkStaleResponse:
    """
    Tandai price_bars kadaluarsa sebagai STALE berdasarkan investment policy.

    Query param opsional: instrument_id — batasi ke satu instrumen.
    Tanpa parameter: proses semua instrumen.

    Idempoten — aman dijalankan berulang.
    """
    from app.ingestion.staleness import mark_stale_from_policy

    result = await mark_stale_from_policy(db, instrument_id=instrument_id)
    await db.commit()

    return MarkStaleResponse(
        marked_stale=result.marked_stale,
        cutoff_date=result.cutoff_date,
        instrument_id=result.instrument_id,
        ran_at=result.ran_at,
    )


@router.post("/refresh-stale", response_model=RefreshStaleResponse)
async def refresh_stale_endpoint(
    days_back: int = Query(default=365, ge=1, le=1825, description="Berapa hari ke belakang untuk di-refresh"),
    limit: int = Query(default=50, ge=1, le=200, description="Maks instrumen per panggilan"),
    db=Depends(get_db),
) -> RefreshStaleResponse:
    """
    Re-ingest OHLCV untuk semua instrumen yang punya bar STALE.

    Memanggil yfinance (atau provider gratis aktif) dengan force=True,
    sehingga bar STALE yang diperbarui kembali menjadi FRESH.
    Idempoten — bar FRESH yang sudah ada tidak digandakan.
    """
    from app.ingestion.staleness import refresh_stale_instruments

    result = await refresh_stale_instruments(db, days_back=days_back, limit=limit)
    await db.commit()

    return RefreshStaleResponse(
        instruments_found=result.instruments_found,
        instruments_refreshed=result.instruments_refreshed,
        bars_added=result.bars_added,
        errors=result.errors,
        ran_at=result.ran_at,
    )


@router.get("/coverage", response_model=CoverageStatusResponse)
async def get_coverage_status(db=Depends(get_db)) -> CoverageStatusResponse:
    """
    Distribusi freshness_status seluruh price_bars.

    Berguna untuk monitoring: berapa bar UNAVAILABLE / QUOTA_EXHAUSTED
    sehingga operator tahu instrumen mana yang berhenti di-refresh.
    """
    from sqlalchemy import func, select
    from app.db.models import PriceBar

    rows = await db.execute(
        select(PriceBar.freshness_status, func.count().label("cnt"))
        .group_by(PriceBar.freshness_status)
    )
    counts: dict[str, int] = {r.freshness_status: r.cnt for r in rows}

    fresh = counts.get("FRESH", 0)
    stale = counts.get("STALE", 0)
    unavail = counts.get("UNAVAILABLE", 0)
    quota = counts.get("QUOTA_EXHAUSTED", 0)
    other = sum(v for k, v in counts.items() if k not in ("FRESH", "STALE", "UNAVAILABLE", "QUOTA_EXHAUSTED"))
    total = fresh + stale + unavail + quota + other

    uniq_unavail = await db.execute(
        select(func.count(func.distinct(PriceBar.instrument_id)))
        .where(PriceBar.freshness_status == "UNAVAILABLE")
    )
    uniq_quota = await db.execute(
        select(func.count(func.distinct(PriceBar.instrument_id)))
        .where(PriceBar.freshness_status == "QUOTA_EXHAUSTED")
    )

    return CoverageStatusResponse(
        fresh=fresh,
        stale=stale,
        unavailable=unavail,
        quota_exhausted=quota,
        other=other,
        total=total,
        stale_pct=round(stale / total * 100, 1) if total else 0.0,
        unavailable_instruments=uniq_unavail.scalar_one() or 0,
        quota_instruments=uniq_quota.scalar_one() or 0,
    )


@router.get("/provider-quota", response_model=ProviderQuotaResponse)
async def get_provider_quota() -> ProviderQuotaResponse:
    """
    Daily call stats per provider dari in-process quota tracker.

    Berguna untuk memantau seberapa banyak panggilan ke yfinance / openbb hari ini
    dan apakah ada yang sudah mencapai batas harian (quota_exhausted=true).
    Counter reset otomatis setiap pergantian hari.
    """
    registry = get_provider_registry()
    tracker = get_quota_tracker()
    stats = tracker.all_stats()

    rows: list[ProviderQuotaRow] = []
    for s in stats:
        try:
            provider = registry.get_by_name(s.provider_name)
            cap = provider.capability() if provider else None
        except Exception:
            cap = None
        quota_per_day = cap.quota_per_day if cap else None
        exhausted = tracker.is_quota_exhausted(s.provider_name, cap)
        rows.append(ProviderQuotaRow(
            provider_name=s.provider_name,
            calls_today=s.calls_today,
            quota_per_day=quota_per_day,
            quota_exhausted=exhausted,
            date_str=s.date_str,
        ))

    total = sum(r.calls_today for r in rows)
    return ProviderQuotaResponse(
        providers=rows,
        total_calls_today=total,
        as_of=datetime.now(tz=timezone.utc),
    )


@router.get("/provider-stats", response_model=ProviderSuccessResponse)
async def get_provider_stats() -> ProviderSuccessResponse:
    """
    Success/failure rate per provider hari ini.

    Menunjukkan berapa kali tiap provider berhasil mengembalikan bar (success)
    vs gagal dengan exception (failure). Berguna untuk mendeteksi provider
    yang tidak reliabel tanpa harus cek log manual.
    """
    from app.providers.success_tracker import get_success_tracker

    tracker = get_success_tracker()
    stats = tracker.all_stats()

    rows = [
        ProviderSuccessRow(
            provider_name=s.provider_name,
            date_str=s.date_str,
            calls_succeeded=s.calls_succeeded,
            calls_failed=s.calls_failed,
            total_calls=s.total_calls,
            success_rate=s.success_rate,
            bars_fetched=s.bars_fetched,
            last_success_at=s.last_success_at,
            last_failure_at=s.last_failure_at,
            last_error=s.last_error,
        )
        for s in stats
    ]
    return ProviderSuccessResponse(
        providers=rows,
        as_of=datetime.now(tz=timezone.utc),
    )


@router.get("/gaps", response_model=DataGapsResponse)
async def get_data_gaps(
    threshold_pct: float = Query(default=10.0, ge=0, le=100, description="Laporkan instrumen dengan gap >= nilai ini (%)"),
    min_history: int = Query(default=30, ge=1, description="Abaikan instrumen dengan history < N hari"),
    limit: int = Query(default=50, ge=1, le=200, description="Maks instrumen dilaporkan"),
    db=Depends(get_db),
) -> DataGapsResponse:
    """
    Deteksi instrumen dengan data OHLCV tidak lengkap (gap).

    Gap dihitung sebagai selisih antara jumlah bar aktual (FRESH/STALE)
    dan estimasi hari kerja * 0.90 dalam rentang tanggal instrumen tersebut.
    Berguna untuk menemukan instrumen yang perlu di-refresh manual.
    """
    from app.analytics.gap_detector import detect_data_gaps

    result = await detect_data_gaps(
        db,
        threshold_pct=threshold_pct,
        min_days_history=min_history,
        limit=limit,
    )

    return DataGapsResponse(
        reports=[
            GapReportRow(
                instrument_id=r.instrument_id,
                canonical_symbol=r.canonical_symbol,
                exchange=r.exchange,
                bar_count=r.bar_count,
                expected_bars=r.expected_bars,
                gap_pct=r.gap_pct,
                first_date=r.first_date,
                last_date=r.last_date,
                history_days=r.history_days,
                severity=r.severity,
            )
            for r in result.reports
        ],
        instruments_checked=result.instruments_checked,
        with_gaps=result.with_gaps,
        ran_at=result.ran_at,
    )


@router.post("/gaps/heal", response_model=HealGapsResponse)
async def heal_gaps_endpoint(
    threshold_pct: float = Query(default=10.0, ge=0, le=100, description="Heal instrumen dengan gap >= nilai ini (%)"),
    min_history: int = Query(default=30, ge=1, description="Abaikan instrumen baru"),
    limit: int = Query(default=20, ge=1, le=100, description="Maks instrumen per panggilan"),
    db=Depends(get_db),
) -> HealGapsResponse:
    """
    Deteksi gap OHLCV lalu re-ingest instrumen terburuk secara otomatis.

    Menggunakan fallback chain (FREE-14) untuk mencoba semua provider gratis.
    Force=True memastikan bar yang sebelumnya hilang akan ditulis ke DB.
    Idempoten — bar yang sudah ada tidak digandakan.
    """
    from app.analytics.gap_healer import heal_data_gaps

    result = await heal_data_gaps(
        db,
        threshold_pct=threshold_pct,
        min_days_history=min_history,
        limit=limit,
    )
    await db.commit()

    return HealGapsResponse(
        instruments_found=result.instruments_found,
        instruments_healed=result.instruments_healed,
        bars_added=result.bars_added,
        errors=result.errors,
        ran_at=result.ran_at,
    )


@router.get("/stale-instruments")
async def list_stale_instruments(
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
) -> StaleInstrumentsResponse:
    """
    Daftar instrumen dengan bar STALE, diurutkan berdasarkan jumlah bar stale (desc).
    Berguna untuk melihat instrumen mana yang perlu di-refresh segera.
    """
    from sqlalchemy import func, select, case
    from app.db.models import Instrument, PriceBar

    stmt = (
        select(
            Instrument.id.label("instrument_id"),
            Instrument.canonical_symbol,
            Instrument.exchange,
            func.count(PriceBar.id).label("total_count"),
            func.sum(
                case((PriceBar.freshness_status == "STALE", 1), else_=0)
            ).label("stale_count"),
            func.sum(
                case((PriceBar.freshness_status == "FRESH", 1), else_=0)
            ).label("fresh_count"),
            func.max(
                case((PriceBar.freshness_status == "FRESH", PriceBar.session_date), else_=None)
            ).label("last_fresh_date"),
        )
        .join(PriceBar, PriceBar.instrument_id == Instrument.id)
        .group_by(Instrument.id, Instrument.canonical_symbol, Instrument.exchange)
        .having(
            func.sum(case((PriceBar.freshness_status == "STALE", 1), else_=0)) > 0
        )
        .order_by(func.sum(case((PriceBar.freshness_status == "STALE", 1), else_=0)).desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    instruments = []
    total_stale = 0
    for row in rows:
        stale = int(row.stale_count or 0)
        fresh = int(row.fresh_count or 0)
        total = int(row.total_count or 0)
        stale_pct = round(stale / total * 100, 1) if total > 0 else 0.0
        total_stale += stale
        instruments.append(
            StaleInstrumentRow(
                instrument_id=str(row.instrument_id),
                canonical_symbol=row.canonical_symbol,
                exchange=row.exchange,
                stale_count=stale,
                fresh_count=fresh,
                total_count=total,
                stale_pct=stale_pct,
                last_fresh_date=str(row.last_fresh_date) if row.last_fresh_date else None,
            )
        )

    return StaleInstrumentsResponse(
        instruments=instruments,
        total_instruments=len(instruments),
        total_stale_bars=total_stale,
        ran_at=datetime.now(tz=timezone.utc),
    )


@router.post("/refresh-batch", response_model=BatchRefreshResponse)
async def refresh_batch(
    symbols: list[str] = Query(default=[], description="Simbol yang ingin di-refresh. Kosong = ambil instrumen paling stale."),
    limit: int = Query(default=10, ge=1, le=50, description="Maks instrumen saat symbols kosong"),
    days_back: int = Query(default=365, ge=30, le=1825, description="Rentang tanggal re-ingest"),
    db=Depends(get_db),
) -> BatchRefreshResponse:
    """
    Re-ingest OHLCV untuk daftar simbol sekaligus via fallback chain.

    Jika `symbols` diisi: refresh tepat simbol tersebut.
    Jika kosong: ambil instrumen paling stale (urut stale_count desc) sampai `limit`.
    Idempoten — bar FRESH yang sudah ada tidak digandakan.
    """
    from datetime import date, timedelta
    from sqlalchemy import func, select, case
    from app.db.models import Instrument, PriceBar

    today = date.today()
    start_date = today - timedelta(days=days_back)

    # Kumpulkan instrument objects
    instruments_to_refresh: list[tuple] = []  # (canonical_symbol, instrument | None)

    if symbols:
        for sym in symbols:
            instr = await resolve_instrument(db, sym)
            instruments_to_refresh.append((sym, instr))
    else:
        # Ambil instrumen paling stale dari DB
        stmt = (
            select(
                Instrument.id,
                Instrument.canonical_symbol,
                Instrument.exchange,
                func.sum(
                    case((PriceBar.freshness_status == "STALE", 1), else_=0)
                ).label("stale_count"),
            )
            .join(PriceBar, PriceBar.instrument_id == Instrument.id)
            .group_by(Instrument.id, Instrument.canonical_symbol, Instrument.exchange)
            .having(func.sum(case((PriceBar.freshness_status == "STALE", 1), else_=0)) > 0)
            .order_by(func.sum(case((PriceBar.freshness_status == "STALE", 1), else_=0)).desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        for row in rows:
            instr = await resolve_instrument(db, row.canonical_symbol)
            instruments_to_refresh.append((row.canonical_symbol, instr))

    results: list[BatchRefreshItemResult] = []

    for sym, instr in instruments_to_refresh:
        if instr is None:
            results.append(BatchRefreshItemResult(
                canonical_symbol=sym,
                status="not_found",
                message=f"Instrumen '{sym}' tidak ditemukan di database",
            ))
            continue

        market = instr.exchange if instr.exchange in ("IDX", "US") else "IDX"
        try:
            fallback_result = await ingest_with_fallback(
                db, instr, market, start=start_date, end=today, force=True
            )
            if fallback_result and fallback_result.bars_added > 0:
                results.append(BatchRefreshItemResult(
                    canonical_symbol=instr.canonical_symbol,
                    status="ok",
                    bars_added=fallback_result.bars_added,
                    provider_used=fallback_result.provider_used,
                ))
            else:
                results.append(BatchRefreshItemResult(
                    canonical_symbol=instr.canonical_symbol,
                    status="no_data",
                    message="Provider tidak mengembalikan bar baru",
                ))
        except Exception as exc:
            log.warning("refresh_batch.error", symbol=sym, error=str(exc))
            results.append(BatchRefreshItemResult(
                canonical_symbol=instr.canonical_symbol,
                status="error",
                message=str(exc),
            ))

    await db.commit()

    succeeded = sum(1 for r in results if r.status == "ok")
    return BatchRefreshResponse(
        results=results,
        total_requested=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        total_bars_added=sum(r.bars_added for r in results),
        ran_at=datetime.now(tz=timezone.utc),
    )


@router.post("/reset-quota", response_model=ResetQuotaResponse)
async def reset_quota_endpoint(db=Depends(get_db)) -> ResetQuotaResponse:
    """
    Reset semua bar QUOTA_EXHAUSTED → STALE agar bisa di-refresh kembali.

    Gunakan setelah rate-limit yfinance berakhir (biasanya setelah 24 jam).
    Bar UNAVAILABLE tidak tersentuh — mereka memang tidak tersedia di provider.
    """
    from datetime import timezone
    from sqlalchemy import update
    from app.db.models import PriceBar

    stmt = (
        update(PriceBar)
        .where(PriceBar.freshness_status == "QUOTA_EXHAUSTED")
        .values(freshness_status="STALE")
    )
    result = await db.execute(stmt)
    await db.commit()

    return ResetQuotaResponse(
        bars_reset=result.rowcount,
        ran_at=datetime.now(tz=timezone.utc),
    )
