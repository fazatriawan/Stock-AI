"""
Staleness Marking & Refresh Service — FREE-07/FREE-08.

Menandai price_bars yang sudah melewati batas freshness sebagai STALE,
dan me-refresh instrumen dengan bar STALE via provider gratis (yfinance).

Prinsip:
- Hanya bar FRESH yang di-update ke STALE. Bar UNAVAILABLE / QUOTA_EXHAUSTED tidak di-override.
- Cutoff = today() - max_staleness_days (dari investment policy, default 3).
- Idempoten — aman dijalankan berulang.
- Tidak pernah menghapus data — refresh meng-upsert bar baru/update yang kadaluarsa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.investment_policy import get_or_create_default
from app.ingestion.empty_ingest import classify_empty_ingest, mark_empty_bars
from app.ingestion.ohlcv import ingest_ohlcv
from app.providers.registry import get_provider_registry

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


# ---------------------------------------------------------------------------
# FREE-08: Bulk refresh stale instruments
# ---------------------------------------------------------------------------

@dataclass
class RefreshStaleResult:
    instruments_found: int
    instruments_refreshed: int
    bars_added: int
    errors: list[str] = field(default_factory=list)
    ran_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


async def refresh_stale_instruments(
    db: AsyncSession,
    days_back: int = 365,
    limit: int = 50,
) -> RefreshStaleResult:
    """
    Temukan instrumen dengan bar STALE, re-ingest via provider gratis.

    - Mencari instrument_id distinct yang punya bar STALE.
    - Untuk setiap instrumen, panggil ingest_ohlcv dengan force=True.
      Upsert menulis freshness_status=FRESH sehingga bar lama yang terupdate jadi FRESH kembali.
    - limit: maksimum instrumen yang diproses per panggilan (hindari timeout).
    - Tidak pernah menghapus data.
    """
    from app.db.models import Instrument, PriceBar

    result = RefreshStaleResult(instruments_found=0, instruments_refreshed=0, bars_added=0)

    # Ambil instrument_id dengan bar STALE
    stale_rows = await db.execute(
        select(PriceBar.instrument_id)
        .where(PriceBar.freshness_status == "STALE")
        .distinct()
        .limit(limit)
    )
    instrument_ids = [r[0] for r in stale_rows.fetchall()]
    result.instruments_found = len(instrument_ids)

    if not instrument_ids:
        log.info("refresh_stale.no_stale_instruments")
        return result

    # Ambil Instrument objects
    instr_rows = await db.execute(
        select(Instrument).where(Instrument.id.in_(instrument_ids))
    )
    instruments = instr_rows.scalars().all()

    registry = get_provider_registry()
    end = date.today()
    start = end - timedelta(days=days_back)

    for instr in instruments:
        market = "IDX" if instr.exchange in ("IDX", "BEI") else "US"
        provider = registry.get_primary(market)
        try:
            ingest_result = await ingest_ohlcv(db, instr, provider, start, end, force=True)
            if ingest_result.inserted == 0 and ingest_result.skipped == 0:
                # Provider kembali kosong — klasifikasikan dan tandai terminal
                reason = classify_empty_ingest(instr.canonical_symbol, None)
                if reason != "STALE":
                    await mark_empty_bars(db, instr.id, reason)
                    log.info(
                        "refresh_stale.empty_marked",
                        symbol=instr.canonical_symbol,
                        reason=reason,
                    )
            else:
                result.instruments_refreshed += 1
                result.bars_added += ingest_result.inserted
                log.info(
                    "refresh_stale.instrument_ok",
                    symbol=instr.canonical_symbol,
                    inserted=ingest_result.inserted,
                )
        except Exception as exc:
            reason = classify_empty_ingest(instr.canonical_symbol, exc)
            if reason != "STALE":
                try:
                    await mark_empty_bars(db, instr.id, reason)
                except Exception:
                    pass
            msg = f"{instr.canonical_symbol}: {exc}"
            result.errors.append(msg)
            log.warning("refresh_stale.instrument_error", symbol=instr.canonical_symbol, error=str(exc))

    log.info(
        "refresh_stale.complete",
        found=result.instruments_found,
        refreshed=result.instruments_refreshed,
        bars_added=result.bars_added,
        errors=len(result.errors),
    )
    return result
