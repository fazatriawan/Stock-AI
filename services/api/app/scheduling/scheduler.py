"""
APScheduler setup — R13.

Jobs terjadwal:
  1. backup_job     — backup DB harian (02:00 WIB)
  2. health_probe   — probe semua provider setiap 15 menit
  3. price_refresh  — refresh harga posisi aktif tiap hari bursa (17:00 WIB)

Prinsip keamanan:
- Tidak ada auto-trade atau aksi finansial — hanya maintenance
- Backup gagal tidak crash server — log error
- Job overlap dicegah dengan coalesce=True + max_instances=1
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.config import get_settings as _get_settings

log = structlog.get_logger(__name__)

BACKUP_SENTINEL_PATH = Path(os.environ.get("BACKUP_DIR", "backups")) / ".last_backup"
BACKUP_SCRIPT_PATH = Path(__file__).resolve().parents[4] / "scripts" / "backup.sh"


async def _run_backup() -> None:
    """
    Jalankan backup.sh sebagai subprocess.
    Tulis sentinel file setelah sukses.
    Gagal graceful — tidak crash server.
    """
    if not BACKUP_SCRIPT_PATH.exists():
        log.warning("backup.job.script_not_found", path=str(BACKUP_SCRIPT_PATH))
        return

    db_url = os.environ.get("DATABASE_URL_SYNC", "")
    if not db_url.startswith("postgres"):
        log.info("backup.job.skip", reason="DATABASE_URL_SYNC bukan PostgreSQL")
        return

    try:
        result = subprocess.run(
            ["bash", str(BACKUP_SCRIPT_PATH)],
            capture_output=True,
            text=True,
            timeout=300,  # max 5 menit
            env={**os.environ},
        )
        if result.returncode == 0:
            # Tulis sentinel
            BACKUP_SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            BACKUP_SENTINEL_PATH.write_text(datetime.utcnow().isoformat() + "+00:00")
            log.info("backup.job.success")
        else:
            log.error("backup.job.failed", returncode=result.returncode, stderr=result.stderr[:500])
    except subprocess.TimeoutExpired:
        log.error("backup.job.timeout")
    except Exception as exc:
        log.error("backup.job.error", error=str(exc))


async def _run_health_probe() -> None:
    """Probe semua provider — update circuit breaker state."""
    try:
        from app.providers.registry import get_provider_registry
        registry = get_provider_registry()
        results = registry.all_health()
        degraded = [h.provider for h in results if h.status.value != "OK"]
        if degraded:
            log.warning("health_probe.degraded", providers=degraded)
        else:
            log.debug("health_probe.all_ok", count=len(results))
    except Exception as exc:
        log.error("health_probe.error", error=str(exc))


async def _run_intraday_poll() -> None:
    """
    Ambil harga terkini setiap 5 menit saat jam bursa berlangsung.
    Upsert ke price_bars dengan provider='yfinance_intraday'.
    """
    try:
        from app.ingestion.intraday import update_latest_prices, is_idx_market_open, is_us_market_open
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        if not is_idx_market_open(now) and not is_us_market_open(now):
            log.debug("intraday_poll.skip", reason="all_markets_closed")
            return
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await update_latest_prices(db)
        log.debug("intraday_poll.done", **result)
    except Exception as exc:
        log.error("intraday_poll.error", error=str(exc))


async def _run_weekly_fundamental_refresh() -> None:
    """
    Refresh fundamental IDX setiap Minggu pagi 08:00 WIB.
    Hanya jika Sectors API atau yfinance tersedia.
    """
    try:
        from app.providers.registry import get_provider_registry
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import select
        from app.db.models import Instrument

        registry = get_provider_registry()
        provider = registry.get_fundamental_provider("IDX")

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Instrument).where(Instrument.status == "ACTIVE", Instrument.exchange == "IDX")
            )
            instruments = result.scalars().all()

        if not instruments:
            log.info("weekly_fundamental.skip", reason="no_instruments")
            return

        log.info("weekly_fundamental.start", count=len(instruments))

        from app.ingestion.fundamentals import ingest_fundamentals
        async with AsyncSessionLocal() as db:
            for instr in instruments:
                try:
                    await ingest_fundamentals(db, instr, provider)
                except Exception as exc:
                    log.warning("weekly_fundamental.instrument_error",
                                symbol=instr.canonical_symbol, error=str(exc))
            await db.commit()

        log.info("weekly_fundamental.done", count=len(instruments))
    except Exception as exc:
        log.error("weekly_fundamental.error", error=str(exc))


async def _run_idx_bootstrap_check() -> None:
    """
    Senin pagi 06:00 WIB: cek apakah ada instrumen IDX baru yang perlu ditambah.
    Hanya run jika jumlah instrumen di DB < 50 (bootstrap awal).
    """
    try:
        from sqlalchemy import select, func
        from app.db.models import Instrument
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            count_result = await db.execute(
                select(func.count()).select_from(Instrument).where(
                    Instrument.exchange == "IDX", Instrument.status == "ACTIVE"
                )
            )
            count = count_result.scalar_one()

        if count >= 50:
            log.debug("idx_bootstrap_check.skip", reason="enough_instruments", count=count)
            return

        log.info("idx_bootstrap_check.running", current_count=count)
        from app.ingestion.idx_full_bootstrap import run_idx_full_bootstrap
        async with AsyncSessionLocal() as db:
            summary = await run_idx_full_bootstrap(db)
        log.info("idx_bootstrap_check.done", **summary)
    except Exception as exc:
        log.error("idx_bootstrap_check.error", error=str(exc))


_scheduler: Optional[AsyncIOScheduler] = None


def create_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")

    # Backup harian 02:00 WIB
    _scheduler.add_job(
        _run_backup,
        trigger=CronTrigger(hour=2, minute=0, timezone="Asia/Jakarta"),
        id="daily_backup",
        name="Daily DB Backup",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Provider health probe setiap 15 menit
    _scheduler.add_job(
        _run_health_probe,
        trigger=CronTrigger(minute="*/15"),
        id="health_probe",
        name="Provider Health Probe",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    # Intraday polling setiap 5 menit (jam bursa IDX & NYSE)
    settings = _get_settings()
    if settings.intraday_polling_enabled:
        _scheduler.add_job(
            _run_intraday_poll,
            trigger=CronTrigger(minute="*/5"),
            id="intraday_poll",
            name="Intraday Price Poll (5m)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=60,
        )

    # Weekly fundamental refresh — Minggu 08:00 WIB
    _scheduler.add_job(
        _run_weekly_fundamental_refresh,
        trigger=CronTrigger(day_of_week="sun", hour=8, minute=0, timezone="Asia/Jakarta"),
        id="weekly_fundamental",
        name="Weekly IDX Fundamental Refresh",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=7200,
    )

    # IDX bootstrap check — Senin 06:00 WIB (hanya jika DB < 50 instrumen)
    _scheduler.add_job(
        _run_idx_bootstrap_check,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=0, timezone="Asia/Jakarta"),
        id="idx_bootstrap_check",
        name="IDX Bootstrap Check",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    all_jobs = ["daily_backup", "health_probe", "weekly_fundamental", "idx_bootstrap_check"]
    if settings.intraday_polling_enabled:
        all_jobs.append("intraday_poll")
    log.info("scheduler.created", jobs=all_jobs)
    return _scheduler


def get_scheduler_jobs() -> list[dict]:
    """Ambil status semua scheduled jobs untuk ops monitor."""
    if _scheduler is None:
        return []
    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_at": next_run.isoformat() if next_run else None,
            "trigger": str(job.trigger),
        })
    return jobs
