"""
Admin routes untuk trigger ingestion manual.
Di production, ingestion dipanggil oleh scheduler — bukan dari UI user.
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.ingestion.bootstrap import bootstrap_instruments, bootstrap_ohlcv

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/bootstrap")
async def trigger_bootstrap(
    background_tasks: BackgroundTasks,
    use_mock: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Bootstrap instruments dan OHLCV dari provider nyata (default) atau mock.
    Idempotent — aman dijalankan berkali-kali.
    use_mock=False → yfinance jika YFINANCE_ENABLED=true, fallback mock jika tidak.
    use_mock=True  → paksa pakai mock (untuk testing/offline).
    """
    symbols = await bootstrap_instruments(db, use_mock=use_mock)
    background_tasks.add_task(bootstrap_ohlcv, db, days_back=365, use_mock=use_mock)
    return {
        "message": "Bootstrap dimulai",
        "instruments_loaded": len(symbols),
        "ohlcv_job": "running in background",
        "data_source": "mock" if use_mock else "live_provider",
    }


@router.post("/bootstrap-mock")
async def trigger_bootstrap_mock(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bootstrap dengan data sintetis — untuk testing/development offline."""
    symbols = await bootstrap_instruments(db, use_mock=True)
    background_tasks.add_task(bootstrap_ohlcv, db, days_back=365, use_mock=True)
    return {
        "message": "Bootstrap mock dimulai",
        "instruments_loaded": len(symbols),
        "ohlcv_job": "running in background",
        "data_source": "mock",
        "warning": "Data sintetis — tidak mencerminkan kondisi pasar nyata",
    }
