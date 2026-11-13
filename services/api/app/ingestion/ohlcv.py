"""
Ingestion job untuk OHLCV.
Idempotent: bar yang sudah ada (instrument_id + session_date + provider) tidak diinsert ulang.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Instrument, PriceBar
from app.domain.calendar import MarketCalendar
from app.providers.base import Bar, MarketDataProvider

logger = get_logger(__name__)


class OHLCVIngestionResult:
    def __init__(self) -> None:
        self.inserted: int = 0
        self.skipped: int = 0
        self.validation_errors: list[str] = []
        self.provider: str = ""
        self.instrument_id: str = ""
        self.date_range: tuple[date, date] | None = None

    def __repr__(self) -> str:
        return (
            f"OHLCVIngestionResult(inserted={self.inserted}, skipped={self.skipped}, "
            f"errors={len(self.validation_errors)}, provider={self.provider})"
        )


async def ingest_ohlcv(
    db: AsyncSession,
    instrument: Instrument,
    provider: MarketDataProvider,
    start: date,
    end: date,
    force: bool = False,
) -> OHLCVIngestionResult:
    """
    Ingest OHLCV dari provider untuk satu instrument.

    Args:
        force: Jika True, update bar yang sudah ada (berguna jika adj_close berubah karena corporate action).
    """
    result = OHLCVIngestionResult()
    result.provider = provider.name
    result.instrument_id = instrument.id
    result.date_range = (start, end)

    # Fetch dari provider
    try:
        bars = provider.get_ohlcv(instrument.canonical_symbol, start, end)
    except Exception as e:
        logger.error("Provider error saat fetch OHLCV", instrument=instrument.canonical_symbol, error=str(e))
        result.validation_errors.append(f"provider_error: {e}")
        return result

    if not bars:
        logger.info("Tidak ada bar dari provider", instrument=instrument.canonical_symbol, start=start, end=end)
        return result

    # Validasi tiap bar
    valid_bars: list[Bar] = []
    for bar in bars:
        errors = bar.validate()
        if errors:
            result.validation_errors.extend([f"{bar.session_date}: {e}" for e in errors])
            continue
        valid_bars.append(bar)

    if not valid_bars:
        return result

    # Cek bar mana yang sudah ada (idempotent)
    existing_dates_result = await db.execute(
        select(PriceBar.session_date).where(
            PriceBar.instrument_id == instrument.id,
            PriceBar.provider == provider.name,
            PriceBar.session_date.between(start, end),
        )
    )
    existing_dates = {row[0] for row in existing_dates_result.fetchall()}

    to_insert: list[dict] = []
    for bar in valid_bars:
        if bar.session_date in existing_dates and not force:
            result.skipped += 1
            continue

        to_insert.append({
            "instrument_id": instrument.id,
            "session_date": bar.session_date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "adj_close": bar.adj_close,
            "volume": bar.volume,
            "provider": bar.provider,
            "is_adjusted": bar.is_adjusted,
            "adjustment_version": bar.adjustment_version,
            "ingested_at": datetime.utcnow(),
            "freshness_status": "FRESH",
        })

    if to_insert:
        if force:
            # Gunakan upsert
            stmt = pg_insert(PriceBar).values(to_insert)
            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument_id", "session_date", "provider"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "adj_close": stmt.excluded.adj_close,
                    "volume": stmt.excluded.volume,
                    "ingested_at": stmt.excluded.ingested_at,
                    "freshness_status": stmt.excluded.freshness_status,
                },
            )
            await db.execute(stmt)
        else:
            stmt = pg_insert(PriceBar).values(to_insert).on_conflict_do_nothing()
            await db.execute(stmt)

        result.inserted = len(to_insert)

    logger.info(
        "OHLCV ingestion selesai",
        instrument=instrument.canonical_symbol,
        inserted=result.inserted,
        skipped=result.skipped,
        errors=len(result.validation_errors),
    )
    return result


async def ingest_bulk_ohlcv(
    db: AsyncSession,
    instruments: list[Instrument],
    provider: MarketDataProvider,
    start: date,
    end: date,
) -> list[OHLCVIngestionResult]:
    """Ingest OHLCV untuk banyak instrument sekaligus."""
    results = []
    for instrument in instruments:
        result = await ingest_ohlcv(db, instrument, provider, start, end)
        results.append(result)
        await db.commit()
    return results


def get_staleness_threshold(exchange: str) -> timedelta:
    """Berapa lama sebuah bar dianggap stale."""
    if exchange == "IDX":
        return timedelta(days=3)  # IDX bisa ada gap libur panjang
    return timedelta(days=2)


async def check_data_staleness(
    db: AsyncSession,
    instrument: Instrument,
    reference_date: date | None = None,
) -> dict:
    """Periksa apakah data harga terbaru untuk instrument ini masih fresh."""
    if reference_date is None:
        reference_date = date.today()

    result = await db.execute(
        select(PriceBar.session_date)
        .where(PriceBar.instrument_id == instrument.id)
        .order_by(PriceBar.session_date.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()

    if row is None:
        return {"stale": True, "reason": "no_data", "last_date": None}

    last_date = row
    calendar = MarketCalendar(instrument.exchange if instrument.exchange in ("IDX",) else "NYSE")
    threshold = get_staleness_threshold(instrument.exchange)

    # Cari hari bursa terakhir sebelum reference_date
    prev_trading = calendar.previous_trading_day(reference_date)

    gap = prev_trading - last_date
    if gap > threshold:
        return {
            "stale": True,
            "reason": f"gap_{gap.days}_days",
            "last_date": last_date.isoformat(),
            "expected": prev_trading.isoformat(),
        }

    return {"stale": False, "last_date": last_date.isoformat()}
