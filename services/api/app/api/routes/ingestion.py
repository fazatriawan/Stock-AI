"""
Admin routes untuk trigger ingestion manual.
Di production, ingestion dipanggil oleh scheduler — bukan dari UI user.
"""
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.ingestion.bootstrap import bootstrap_instruments, bootstrap_ohlcv

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/bootstrap")
async def trigger_bootstrap(
    background_tasks: BackgroundTasks,
    use_mock: bool = True,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Bootstrap instruments dan OHLCV dari provider/mock.
    Idempotent — aman dijalankan berkali-kali.
    """
    symbols = await bootstrap_instruments(db, use_mock=use_mock)
    background_tasks.add_task(bootstrap_ohlcv, db, days_back=365, use_mock=use_mock)
    return {
        "message": "Bootstrap dimulai",
        "instruments_loaded": len(symbols),
        "ohlcv_job": "running in background",
    }
