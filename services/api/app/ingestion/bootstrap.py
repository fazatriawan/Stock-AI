"""
Bootstrap instruments dari mock/provider ke database.
Dijalankan saat startup untuk memastikan instrument registry terisi.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.instruments import upsert_instrument
from app.ingestion.ohlcv import ingest_bulk_ohlcv
from app.providers.mock_provider import MOCK_INSTRUMENTS
from app.providers.registry import get_provider_registry

logger = get_logger(__name__)


async def bootstrap_instruments(db: AsyncSession, use_mock: bool = True) -> list[str]:
    """
    Inisialisasi instrument dari provider/mock ke database.
    Kembalikan daftar canonical_symbol yang diinsert/update.
    """
    registry = get_provider_registry()
    provider = registry.get_by_name("mock") if use_mock else registry.get_primary("IDX")

    if provider is None:
        logger.error("Tidak ada provider tersedia untuk bootstrap")
        return []

    canonical_symbols = []
    for canonical_symbol, info in MOCK_INSTRUMENTS.items():
        instrument = await upsert_instrument(db, info)
        canonical_symbols.append(instrument.canonical_symbol)
        logger.info("Instrument di-bootstrap", symbol=instrument.canonical_symbol)

    await db.commit()
    logger.info("Bootstrap instruments selesai", count=len(canonical_symbols))
    return canonical_symbols


async def bootstrap_ohlcv(
    db: AsyncSession,
    days_back: int = 365,
    use_mock: bool = True,
) -> None:
    """
    Ingest OHLCV historis untuk semua instrument yang sudah di-bootstrap.
    """
    from app.db.models import Instrument
    from sqlalchemy import select

    registry = get_provider_registry()
    provider = registry.get_by_name("mock") if use_mock else registry.get_primary("IDX")

    if provider is None:
        logger.error("Tidak ada provider untuk OHLCV bootstrap")
        return

    end = date.today()
    start = end - timedelta(days=days_back)

    result = await db.execute(select(Instrument).where(Instrument.status == "ACTIVE"))
    instruments = list(result.scalars().all())

    logger.info("Memulai OHLCV bootstrap", count=len(instruments), start=start, end=end)
    results = await ingest_bulk_ohlcv(db, instruments, provider, start, end)

    total_inserted = sum(r.inserted for r in results)
    total_skipped = sum(r.skipped for r in results)
    logger.info("OHLCV bootstrap selesai", inserted=total_inserted, skipped=total_skipped)
