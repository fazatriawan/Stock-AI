from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.schemas import (
    CSVImportResponse,
    DataHealthResponse,
    DataProviderResponse,
    DataProvidersResponse,
    ProviderHealthResponse,
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
