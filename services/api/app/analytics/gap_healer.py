"""
FREE-18: Gap auto-healer — deteksi + re-ingest instrumen dengan data tidak lengkap.

Memanggil detect_data_gaps lalu mencoba mengisi gap via ingest_with_fallback
(force=True) untuk setiap instrumen yang terdeteksi. Karena force=True, upsert
akan menulis bar baru untuk tanggal yang belum ada di DB, dan memperbarui
freshness_status bar lama ke FRESH.

Prinsip:
- Hanya instrumen dengan severity CRITICAL atau WARNING yang di-heal (OK diabaikan).
- Gunakan first_date instrumen sebagai start ingest — bukan today - 365 —
  agar gap yang jauh di masa lalu juga terisi.
- Error satu instrumen tidak menghentikan yang lain (isolasi).
- Tidak pernah mengeksekusi transaksi broker atau memanggil provider berbayar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.gap_detector import detect_data_gaps
from app.ingestion.provider_fallback import ingest_with_fallback

log = structlog.get_logger(__name__)


@dataclass
class HealResult:
    instruments_found: int = 0    # dengan gap >= threshold
    instruments_healed: int = 0   # berhasil re-ingest
    bars_added: int = 0
    errors: list[str] = field(default_factory=list)
    ran_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


async def heal_data_gaps(
    db: AsyncSession,
    threshold_pct: float = 10.0,
    min_days_history: int = 30,
    limit: int = 20,
) -> HealResult:
    """
    Deteksi dan perbaiki gap data OHLCV secara otomatis.

    Args:
        db: AsyncSession
        threshold_pct: hanya heal instrumen dengan gap >= nilai ini (%)
        min_days_history: abaikan instrumen baru
        limit: maks instrumen yang di-heal per panggilan

    Returns:
        HealResult dengan ringkasan operasi
    """
    gap_result = await detect_data_gaps(
        db,
        threshold_pct=threshold_pct,
        min_days_history=min_days_history,
        limit=limit,
    )

    # Hanya heal instrumen yang memang punya gap nyata
    to_heal = [r for r in gap_result.reports if r.severity in ("CRITICAL", "WARNING")]

    result = HealResult(instruments_found=len(to_heal))

    if not to_heal:
        log.info("gap_healer.nothing_to_heal")
        return result

    # Ambil Instrument objects untuk dapat exchange info
    from sqlalchemy import select
    from app.db.models import Instrument

    ids = [r.instrument_id for r in to_heal]
    instr_rows = await db.execute(
        select(Instrument).where(Instrument.id.in_(ids))
    )
    instr_map = {i.id: i for i in instr_rows.scalars().all()}

    today = date.today()

    for gap in to_heal:
        instr = instr_map.get(gap.instrument_id)
        if instr is None:
            result.errors.append(f"{gap.canonical_symbol}: instrumen tidak ditemukan di DB")
            continue

        market = "IDX" if instr.exchange in ("IDX", "BEI") else "US"
        start = gap.first_date  # ingest dari bar pertama yang diketahui

        try:
            fb_result = await ingest_with_fallback(
                db, instr, market, start, today, force=True
            )
            if fb_result is None:
                log.info(
                    "gap_healer.provider_empty",
                    symbol=gap.canonical_symbol,
                    gap_pct=gap.gap_pct,
                )
                result.errors.append(f"{gap.canonical_symbol}: semua provider kosong")
            else:
                result.instruments_healed += 1
                result.bars_added += fb_result.ohlcv.inserted
                log.info(
                    "gap_healer.healed",
                    symbol=gap.canonical_symbol,
                    gap_pct=gap.gap_pct,
                    bars_added=fb_result.ohlcv.inserted,
                    provider=fb_result.provider_used,
                )
        except Exception as exc:
            msg = f"{gap.canonical_symbol}: {exc}"
            result.errors.append(msg)
            log.warning("gap_healer.error", symbol=gap.canonical_symbol, error=str(exc))

    log.info(
        "gap_healer.complete",
        found=result.instruments_found,
        healed=result.instruments_healed,
        bars_added=result.bars_added,
        errors=len(result.errors),
    )
    return result
