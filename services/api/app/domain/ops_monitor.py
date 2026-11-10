"""
Ops Monitor — R13.

Agregasi status sistem untuk endpoint /admin/ops:
- Provider health + circuit breaker
- DB connectivity
- AI budget state
- Backup status (waktu backup terakhir dari file sentinel)
- Scheduled job status (APScheduler)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# Path sentinel file yang ditulis backup.sh setelah backup sukses
BACKUP_SENTINEL_PATH = Path(os.environ.get("BACKUP_DIR", "backups")) / ".last_backup"


def get_backup_status() -> dict:
    """
    Baca waktu backup terakhir dari sentinel file.
    backup.sh menulis timestamp ISO ke file ini setelah sukses.
    """
    if not BACKUP_SENTINEL_PATH.exists():
        return {
            "last_backup_at": None,
            "status": "NEVER",
            "age_hours": None,
        }
    try:
        content = BACKUP_SENTINEL_PATH.read_text().strip()
        last_at = datetime.fromisoformat(content)
        age = (datetime.now(tz=timezone.utc) - last_at).total_seconds() / 3600
        status = "OK" if age < 25 else ("WARNING" if age < 72 else "STALE")
        return {
            "last_backup_at": content,
            "status": status,
            "age_hours": round(age, 1),
        }
    except Exception as exc:
        return {
            "last_backup_at": None,
            "status": "ERROR",
            "age_hours": None,
            "error": str(exc),
        }


async def get_db_status(db_url: str) -> dict:
    """Cek konektivitas DB via ping SELECT 1."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine(db_url, pool_size=1, max_overflow=0)
        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return {"status": "OK", "error": None}
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)[:200]}


def get_ai_budget_status() -> dict:
    """Ambil status AI budget dari circuit breaker AI."""
    try:
        from app.ai.adapter import _budget, MAX_CALLS_PER_HOUR, MAX_TOKENS_PER_HOUR
        return {
            "calls_this_hour": _budget.calls_this_hour,
            "max_calls_per_hour": MAX_CALLS_PER_HOUR,
            "tokens_this_hour": _budget.tokens_this_hour,
            "max_tokens_per_hour": MAX_TOKENS_PER_HOUR,
            "consecutive_errors": _budget.consecutive_errors,
            "last_reset_at": _budget.last_reset_at.isoformat() if _budget.last_reset_at else None,
        }
    except Exception:
        return {"status": "unavailable"}


def get_scheduler_status() -> list[dict]:
    """
    Ambil status scheduled jobs dari APScheduler jika aktif.
    Scheduler di-attach ke app state di lifespan.
    """
    try:
        from app.scheduling.scheduler import get_scheduler_jobs
        return get_scheduler_jobs()
    except Exception:
        return []


async def build_ops_report(db_url: Optional[str] = None) -> dict:
    """
    Susun laporan ops lengkap. Dipakai oleh GET /admin/ops.
    """
    from app.providers.registry import get_provider_registry

    registry = get_provider_registry()
    provider_health = registry.all_health()
    cb_statuses = registry.all_circuit_breaker_statuses()

    db_status = {}
    if db_url:
        db_status = await get_db_status(db_url)

    return {
        "as_of": datetime.now(tz=timezone.utc).isoformat(),
        "providers": [
            {
                "name": h.provider,
                "status": h.status.value,
                "last_error": h.last_error,
                "latency_ms": h.latency_ms,
                "notes": h.notes,
            }
            for h in provider_health
        ],
        "circuit_breakers": cb_statuses,
        "database": db_status,
        "ai_budget": get_ai_budget_status(),
        "backup": get_backup_status(),
        "scheduled_jobs": get_scheduler_status(),
    }
