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

# Lazy import agar tidak memperkenalkan circular import saat modul dimuat
def _tracker():
    from app.scheduling.job_history import get_job_history_tracker
    return get_job_history_tracker()


async def _run_backup() -> None:
    """
    Jalankan backup.sh sebagai subprocess.
    Tulis sentinel file setelah sukses.
    Gagal graceful — tidak crash server.
    """
    rec = _tracker().start_run("backup")
    if not BACKUP_SCRIPT_PATH.exists():
        log.warning("backup.job.script_not_found", path=str(BACKUP_SCRIPT_PATH))
        _tracker().finish_run(rec, status="error", error="script_not_found")
        return

    db_url = os.environ.get("DATABASE_URL_SYNC", "")
    if not db_url.startswith("postgres"):
        log.info("backup.job.skip", reason="DATABASE_URL_SYNC bukan PostgreSQL")
        _tracker().finish_run(rec, status="ok", summary={"skipped": True, "reason": "not_postgres"})
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
            _tracker().finish_run(rec, status="ok", summary={"returncode": 0})
        else:
            log.error("backup.job.failed", returncode=result.returncode, stderr=result.stderr[:500])
            _tracker().finish_run(rec, status="error", error=f"returncode={result.returncode}")
    except subprocess.TimeoutExpired:
        log.error("backup.job.timeout")
        _tracker().finish_run(rec, status="error", error="timeout")
    except Exception as exc:
        log.error("backup.job.error", error=str(exc))
        _tracker().finish_run(rec, status="error", error=str(exc))


async def _run_health_probe() -> None:
    """Probe semua provider — update circuit breaker state."""
    rec = _tracker().start_run("health_probe")
    try:
        from app.providers.registry import get_provider_registry
        registry = get_provider_registry()
        results = registry.all_health()
        degraded = [h.provider for h in results if h.status.value != "OK"]
        if degraded:
            log.warning("health_probe.degraded", providers=degraded)
        else:
            log.debug("health_probe.all_ok", count=len(results))
        _tracker().finish_run(rec, status="ok", summary={"total": len(results), "degraded": len(degraded)})
    except Exception as exc:
        log.error("health_probe.error", error=str(exc))
        _tracker().finish_run(rec, status="error", error=str(exc))


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
    rec = _tracker().start_run("weekly_fundamental")
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
            _tracker().finish_run(rec, status="ok", summary={"skipped": True, "reason": "no_instruments"})
            return

        log.info("weekly_fundamental.start", count=len(instruments))

        from app.ingestion.fundamentals import ingest_fundamentals
        errors = 0
        async with AsyncSessionLocal() as db:
            for instr in instruments:
                try:
                    await ingest_fundamentals(db, instr, provider)
                except Exception as exc:
                    errors += 1
                    log.warning("weekly_fundamental.instrument_error",
                                symbol=instr.canonical_symbol, error=str(exc))
            await db.commit()

        log.info("weekly_fundamental.done", count=len(instruments))
        _tracker().finish_run(rec, status="ok", summary={"instruments": len(instruments), "errors": errors})
    except Exception as exc:
        log.error("weekly_fundamental.error", error=str(exc))
        _tracker().finish_run(rec, status="error", error=str(exc))


async def _run_gap_heal() -> None:
    """
    Harian 03:30 WIB: auto-heal gap data setelah backup selesai (02:00).
    Memanggil heal_data_gaps() — maks 20 instrumen per run.
    """
    rec = _tracker().start_run("gap_heal")
    try:
        from app.analytics.gap_healer import heal_data_gaps
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await heal_data_gaps(db)
            await db.commit()
        log.info(
            "gap_heal_job.done",
            instruments_found=result.instruments_found,
            instruments_healed=result.instruments_healed,
            bars_added=result.bars_added,
            errors=len(result.errors),
        )
        _tracker().finish_run(rec, status="ok", summary={
            "instruments_found": result.instruments_found,
            "instruments_healed": result.instruments_healed,
            "bars_added": result.bars_added,
            "errors": len(result.errors),
        })
    except Exception as exc:
        log.error("gap_heal_job.error", error=str(exc))
        _tracker().finish_run(rec, status="error", error=str(exc))


async def _run_staleness_mark() -> None:
    """
    Harian 06:30 WIB: tandai price_bars kadaluarsa sebagai STALE.
    Menggunakan max_staleness_days dari investment policy (default 3).
    """
    rec = _tracker().start_run("staleness_mark")
    try:
        from app.db.session import AsyncSessionLocal
        from app.ingestion.staleness import mark_stale_from_policy

        async with AsyncSessionLocal() as db:
            result = await mark_stale_from_policy(db)
            await db.commit()
        log.info("staleness_job.done", marked=result.marked_stale, cutoff=result.cutoff_date.isoformat())
        _tracker().finish_run(rec, status="ok", summary={"marked_stale": result.marked_stale, "cutoff": result.cutoff_date.isoformat()})
    except Exception as exc:
        log.error("staleness_job.error", error=str(exc))
        _tracker().finish_run(rec, status="error", error=str(exc))


async def _run_refresh_stale() -> None:
    """
    Harian 06:35 WIB (5 menit setelah mark-stale): re-ingest instrumen dengan bar STALE.
    Hanya jalan jika yfinance diaktifkan — tidak ada biaya tambahan.
    """
    rec = _tracker().start_run("refresh_stale")
    settings = _get_settings()
    if not settings.yfinance_enabled:
        log.info("refresh_stale_job.skip", reason="yfinance_disabled")
        _tracker().finish_run(rec, status="ok", summary={"skipped": True, "reason": "yfinance_disabled"})
        return
    try:
        from app.db.session import AsyncSessionLocal
        from app.ingestion.staleness import refresh_stale_instruments

        async with AsyncSessionLocal() as db:
            result = await refresh_stale_instruments(db)
            await db.commit()
        log.info(
            "refresh_stale_job.done",
            found=result.instruments_found,
            refreshed=result.instruments_refreshed,
            bars_added=result.bars_added,
        )
        _tracker().finish_run(rec, status="ok", summary={
            "instruments_found": result.instruments_found,
            "instruments_refreshed": result.instruments_refreshed,
            "bars_added": result.bars_added,
        })
    except Exception as exc:
        log.error("refresh_stale_job.error", error=str(exc))
        _tracker().finish_run(rec, status="error", error=str(exc))


async def _run_idx_intraday_close() -> None:
    """
    15:55 WIB: tandai bar intraday IDX sebagai STALE setelah bursa tutup.
    EOD bar resmi akan datang saat refresh_stale berjalan malam ini.
    """
    settings = _get_settings()
    if not settings.intraday_polling_enabled:
        return
    try:
        from app.db.session import AsyncSessionLocal
        from app.ingestion.intraday import mark_intraday_stale

        async with AsyncSessionLocal() as db:
            marked = await mark_intraday_stale(db)
            await db.commit()
        log.info("intraday_close_job.done", market="IDX", marked=marked)
    except Exception as exc:
        log.error("intraday_close_job.error", market="IDX", error=str(exc))


async def _run_us_intraday_close() -> None:
    """
    16:05 EST (21:05 UTC): tandai bar intraday US sebagai STALE setelah NYSE tutup.
    """
    settings = _get_settings()
    if not settings.intraday_polling_enabled:
        return
    try:
        from app.db.session import AsyncSessionLocal
        from app.ingestion.intraday import mark_intraday_stale

        async with AsyncSessionLocal() as db:
            marked = await mark_intraday_stale(db)
            await db.commit()
        log.info("intraday_close_job.done", market="US", marked=marked)
    except Exception as exc:
        log.error("intraday_close_job.error", market="US", error=str(exc))


async def _run_idx_bootstrap_check() -> None:
    """
    Senin pagi 06:00 WIB: cek apakah ada instrumen IDX baru yang perlu ditambah.
    Hanya run jika jumlah instrumen di DB < 50 (bootstrap awal).
    """
    rec = _tracker().start_run("idx_bootstrap_check")
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
            _tracker().finish_run(rec, status="ok", summary={"skipped": True, "count": count})
            return

        log.info("idx_bootstrap_check.running", current_count=count)
        from app.ingestion.idx_full_bootstrap import run_idx_full_bootstrap
        async with AsyncSessionLocal() as db:
            summary = await run_idx_full_bootstrap(db)
        log.info("idx_bootstrap_check.done", **summary)
        _tracker().finish_run(rec, status="ok", summary={"count_before": count, **summary})
    except Exception as exc:
        log.error("idx_bootstrap_check.error", error=str(exc))
        _tracker().finish_run(rec, status="error", error=str(exc))


async def _run_us_bootstrap_check() -> None:
    """
    Senin 06:15 WIB: cek apakah ada instrumen US yang perlu di-bootstrap.
    Hanya run jika jumlah instrumen US di DB < 20 (bootstrap awal).
    """
    rec = _tracker().start_run("us_bootstrap_check")
    settings = _get_settings()
    if not settings.us_bootstrap_enabled:
        log.debug("us_bootstrap_check.skip", reason="us_bootstrap_disabled")
        _tracker().finish_run(rec, status="ok", summary={"skipped": True, "reason": "us_bootstrap_disabled"})
        return
    try:
        from sqlalchemy import select, func
        from app.db.models import Instrument
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            count_result = await db.execute(
                select(func.count()).select_from(Instrument).where(
                    Instrument.exchange.in_(["NASDAQ", "NYSE", "US"]),
                    Instrument.status == "ACTIVE",
                )
            )
            count = count_result.scalar_one()

        if count >= 20:
            log.debug("us_bootstrap_check.skip", reason="enough_instruments", count=count)
            _tracker().finish_run(rec, status="ok", summary={"skipped": True, "count": count})
            return

        log.info("us_bootstrap_check.running", current_count=count)
        from app.ingestion.us_bootstrap import run_us_bootstrap
        async with AsyncSessionLocal() as db:
            summary = await run_us_bootstrap(db)
        log.info("us_bootstrap_check.done", **summary)
        _tracker().finish_run(rec, status="ok", summary={"count_before": count, **summary})
    except Exception as exc:
        log.error("us_bootstrap_check.error", error=str(exc))
        _tracker().finish_run(rec, status="error", error=str(exc))


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
        # IDX market close cleanup — 15:55 WIB
        _scheduler.add_job(
            _run_idx_intraday_close,
            trigger=CronTrigger(hour=15, minute=55, timezone="Asia/Jakarta"),
            id="idx_intraday_close",
            name="IDX Intraday Close Cleanup",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )
        # US market close cleanup — 16:05 EST
        _scheduler.add_job(
            _run_us_intraday_close,
            trigger=CronTrigger(hour=16, minute=5, timezone="America/New_York"),
            id="us_intraday_close",
            name="US Intraday Close Cleanup",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
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

    # US bootstrap check — Senin 06:15 WIB (setelah IDX check, hanya jika DB < 20 instrumen US)
    _scheduler.add_job(
        _run_us_bootstrap_check,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=15, timezone="Asia/Jakarta"),
        id="us_bootstrap_check",
        name="US Bootstrap Check",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Nightly gap heal — 03:30 WIB (setelah backup 02:00 selesai)
    _scheduler.add_job(
        _run_gap_heal,
        trigger=CronTrigger(hour=3, minute=30, timezone="Asia/Jakarta"),
        id="gap_heal",
        name="Nightly Gap Heal",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Staleness marking — harian 06:30 WIB
    _scheduler.add_job(
        _run_staleness_mark,
        trigger=CronTrigger(hour=6, minute=30, timezone="Asia/Jakarta"),
        id="staleness_mark",
        name="Nightly Staleness Mark",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Refresh stale instruments — harian 06:35 WIB (setelah staleness_mark)
    _scheduler.add_job(
        _run_refresh_stale,
        trigger=CronTrigger(hour=6, minute=35, timezone="Asia/Jakarta"),
        id="refresh_stale",
        name="Nightly Stale Refresh",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    all_jobs = [
        "daily_backup", "health_probe", "weekly_fundamental",
        "idx_bootstrap_check", "us_bootstrap_check", "gap_heal",
        "staleness_mark", "refresh_stale",
    ]
    if settings.intraday_polling_enabled:
        all_jobs.extend(["intraday_poll", "idx_intraday_close", "us_intraday_close"])
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
