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


async def _seed_sources(db: AsyncSession) -> None:
    """Seed default data sources agar financial_facts FK constraint terpenuhi."""
    from sqlalchemy import text
    default_sources = [
        ("src_yfinance", "https://finance.yahoo.com", "Yahoo Finance", "yfinance provider"),
        ("src_mock", None, "Mock Provider", "synthetic test data"),
        ("src_sectors", "https://sectors.app", "Sectors.app", "Sectors Financial API"),
        ("src_fred", "https://fred.stlouisfed.org", "Federal Reserve (FRED)", "FRED macro data"),
        ("src_manual", None, "Manual Entry", "data diinput manual"),
    ]
    for src_id, url, publisher, title in default_sources:
        await db.execute(text("""
            INSERT INTO sources (id, url, publisher, title, license_class, primary_or_secondary)
            VALUES (:id, :url, :publisher, :title, 'THIRD_PARTY', 'SECONDARY')
            ON CONFLICT (id) DO NOTHING
        """), {"id": src_id, "url": url, "publisher": publisher, "title": title})


async def bootstrap_instruments(db: AsyncSession, use_mock: bool = False) -> list[str]:
    """
    Inisialisasi instrument dari catalog ke database.
    Catalog instrument selalu dari MOCK_INSTRUMENTS (ticker IDX & US yang didukung).
    Harga OHLCV akan diambil dari provider sesuai use_mock flag.

    Returns daftar canonical_symbol yang diinsert/update.
    """
    await _seed_sources(db)

    canonical_symbols = []
    for canonical_symbol, info in MOCK_INSTRUMENTS.items():
        instrument = await upsert_instrument(db, info)
        canonical_symbols.append(instrument.canonical_symbol)
        logger.info("Instrument di-bootstrap", symbol=instrument.canonical_symbol)

    await db.commit()
    logger.info(
        "Bootstrap instruments selesai",
        count=len(canonical_symbols),
        data_source="mock_ohlcv" if use_mock else "live_ohlcv",
    )
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
