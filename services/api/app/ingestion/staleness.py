"""
Staleness Marking Service — FREE-07.

Menandai price_bars yang sudah melewati batas freshness sebagai STALE.
Prinsip:
- Hanya bar dengan freshness_status=FRESH yang di-update ke STALE.
  Bar UNAVAILABLE / QUOTA_EXHAUSTED tidak di-override.
- Cutoff = today() - max_staleness_days (dari investment policy, default 3).
- Idempoten — aman dijalankan berulang.
- Tidak pernah menghapus data — hanya update status.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.investment_policy import get_or_create_default

log = structlog.get_logger(__name__)

DEFAULT_STALENESS_DAYS = 3


@dataclass
class StalenessMarkResult:
    marked_stale: int
    cutoff_date: date
    instrument_id: Optional[str]   # None = semua instrumen
    ran_at: datetime


async def mark_stale_bars(
    db: AsyncSession,
    max_staleness_days: int = DEFAULT_STALENESS_DAYS,
    instrument_id: Optional[str] = None,
) -> StalenessMarkResult:
    """
    Update freshness_status ke STALE untuk price_bars yang sudah kadaluarsa.

    Args:
        db: AsyncSession
        max_staleness_days: bar dengan session_date < today - days ini menjadi STALE
        instrument_id: batasi ke satu instrumen (None = semua)

    Returns:
        StalenessMarkResult dengan jumlah baris yang diupdate
    """
    from app.db.models import PriceBar

    cutoff = date.today() - timedelta(days=max_staleness_days)

    stmt = (
        update(PriceBar)
        .where(
            PriceBar.freshness_status == "FRESH",
            PriceBar.session_date < cutoff,
        )
        .values(freshness_status="STALE")
    )

    if instrument_id is not None:
        stmt = stmt.where(PriceBar.instrument_id == instrument_id)

    result = await db.execute(stmt)
    marked = result.rowcount

    log.info(
        "staleness.mark_complete",
        marked=marked,
        cutoff=cutoff.isoformat(),
        instrument_id=instrument_id or "all",
        max_staleness_days=max_staleness_days,
    )

    return StalenessMarkResult(
        marked_stale=marked,
        cutoff_date=cutoff,
        instrument_id=instrument_id,
        ran_at=datetime.now(tz=timezone.utc),
    )


async def mark_stale_from_policy(
    db: AsyncSession,
    instrument_id: Optional[str] = None,
) -> StalenessMarkResult:
    """
    Jalankan mark_stale_bars dengan max_staleness_days dari investment policy DB.
    Fallback ke DEFAULT_STALENESS_DAYS jika policy belum ada.
    """
    try:
        policy = await get_or_create_default(db)
        days = int(policy.max_staleness_days)
    except Exception:
        log.warning("staleness.policy_fallback", default_days=DEFAULT_STALENESS_DAYS)
        days = DEFAULT_STALENESS_DAYS

    return await mark_stale_bars(db, max_staleness_days=days, instrument_id=instrument_id)
