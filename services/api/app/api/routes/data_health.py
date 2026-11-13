from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.api.schemas import (
    CSVImportResponse,
    CoverageStatusResponse,
    DataHealthResponse,
    DataProviderResponse,
    DataProvidersResponse,
    FreshnessBreakdown,
    InstrumentFreshnessResponse,
    MarkStaleResponse,
    ProviderHealthResponse,
    RefreshStaleResponse,
)
from app.db.session import get_db
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
