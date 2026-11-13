"""
Admin / Ops routes — R13.

GET /admin/ops  → laporan status sistem lengkap:
  - Provider health + circuit breaker
  - DB connectivity
  - AI budget usage
  - Backup status (last backup, age)
  - Scheduled jobs

Tidak ada autentikasi kuat di V1 (lokal only). Jangan expose ke internet tanpa auth.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Instrument, PriceBar
from app.db.session import get_db
from app.domain.ops_monitor import build_ops_report

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ops")
async def get_ops_status(request: Request) -> dict:
    """
    Status operasional sistem: provider, circuit breaker, DB, AI budget, backup, scheduler.
    """
    settings = get_settings()
    db_url = settings.database_url if hasattr(settings, "database_url") else None
    return await build_ops_report(db_url=db_url)


@router.get("/setup-status")
async def get_setup_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Cek status setup awal: jumlah instrumen dan harga di DB."""
    instr_count = await db.scalar(select(func.count()).select_from(Instrument).where(Instrument.status == "ACTIVE"))
    price_count = await db.scalar(select(func.count()).select_from(PriceBar))
    settings = get_settings()
    return {
        "instruments_loaded": instr_count or 0,
        "price_bars": price_count or 0,
        "yfinance_enabled": getattr(settings, "yfinance_enabled", False),
        "is_ready": (instr_count or 0) > 0,
    }


@router.post("/bootstrap/idx")
async def trigger_idx_bootstrap(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Trigger IDX full bootstrap di background (~30 menit).
    Download histori 200+ saham IDX via yfinance.
    """
    import asyncio
    from app.ingestion.idx_full_bootstrap import run_idx_full_bootstrap

    async def _run() -> None:
        await run_idx_full_bootstrap(db)

    asyncio.create_task(_run())
    return {"status": "triggered", "message": "IDX bootstrap berjalan di background. Cek /admin/setup-status untuk progress."}


@router.post("/bootstrap/us")
async def trigger_us_bootstrap(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Trigger US stocks bootstrap di background (~20 menit).
    Download histori 90 ticker US (S&P 500 pilihan + ETF) via yfinance.
    """
    import asyncio
    from app.ingestion.us_bootstrap import run_us_bootstrap

    async def _run() -> None:
        await run_us_bootstrap(db)

    asyncio.create_task(_run())
    return {"status": "triggered", "message": "US bootstrap berjalan di background. Cek /admin/setup-status untuk progress."}


@router.post("/quota-tracker/reset")
async def reset_quota_tracker() -> dict:
    """
    Reset in-process daily call counter untuk semua provider.

    Counter reset otomatis setiap pergantian hari, tapi endpoint ini berguna
    saat testing atau setelah quota provider diperluas manual oleh operator.
    Tidak mempengaruhi freshness_status di price_bars (gunakan POST /data/reset-quota untuk itu).
    """
    from datetime import datetime, timezone
    from app.providers.quota_tracker import get_quota_tracker

    tracker = get_quota_tracker()
    tracker.reset_all()
    return {
        "status": "reset",
        "message": "In-process quota counter direset. Semua provider kembali ke 0 panggilan hari ini.",
        "reset_at": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.post("/backup/trigger")
async def trigger_backup() -> dict:
    """
    Trigger backup manual secara on-demand (async background task).
    Tidak menunggu selesai — cek /admin/ops untuk status.
    """
    import asyncio
    from app.scheduling.scheduler import _run_backup

    asyncio.create_task(_run_backup())
    return {"status": "triggered", "message": "Backup berjalan di background. Cek /admin/ops untuk status."}
