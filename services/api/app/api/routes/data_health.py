from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.schemas import DataHealthResponse, ProviderHealthResponse
from app.providers.registry import get_provider_registry

router = APIRouter(prefix="/data", tags=["data"])


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
