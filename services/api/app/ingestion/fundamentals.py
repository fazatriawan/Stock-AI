"""
Ingestion job untuk FinancialFact (data fundamental).
Idempotent: fact yang sudah ada (instrument_id + metric + period_end + source_id)
tidak diinsert ulang — gunakan ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import FinancialFact, new_uuid
from app.providers.base import Fact, MarketDataProvider
from app.db.models import Instrument

logger = get_logger(__name__)

# Source ID sentinel untuk provider-sourced facts
PROVIDER_SOURCE_ID: dict[str, str] = {
    "sectors":  "src_sectors",
    "yfinance": "src_yfinance",
    "mock":     "src_mock",
}


async def ingest_fundamentals(
    db: AsyncSession,
    instrument: Instrument,
    provider: MarketDataProvider,
) -> tuple[int, int]:
    """
    Ambil fundamental dari provider dan simpan ke financial_facts.
    Mengembalikan (inserted, skipped).
    """
    as_of = datetime.now(tz=timezone.utc)
    try:
        facts: list[Fact] = provider.get_fundamentals(instrument.canonical_symbol, as_of)
    except Exception as e:
        logger.error("get_fundamentals gagal", symbol=instrument.canonical_symbol, provider=provider.name, error=str(e))
        return 0, 0

    if not facts:
        logger.info("Tidak ada fact dari provider", symbol=instrument.canonical_symbol, provider=provider.name)
        return 0, 0

    source_id = PROVIDER_SOURCE_ID.get(provider.name, f"src_{provider.name}")
    inserted = 0
    skipped = 0

    for fact in facts:
        # Cek apakah sudah ada (unik: instrument_id + metric + period_end + source_id)
        from sqlalchemy import select
        existing = await db.execute(
            select(FinancialFact).where(
                FinancialFact.instrument_id == instrument.id,
                FinancialFact.metric == fact.metric,
                FinancialFact.period_end == fact.period_end,
                FinancialFact.source_id == source_id,
            ).limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue

        db.add(FinancialFact(
            id=new_uuid(),
            instrument_id=instrument.id,
            metric=fact.metric,
            period_start=fact.period_start,
            period_end=fact.period_end,
            filing_date=fact.filing_date,
            available_at=fact.available_at or as_of.date(),
            value=fact.value,
            value_text=fact.value_text,
            unit=fact.unit,
            currency=fact.currency,
            accounting_basis=fact.accounting_basis,
            source_id=source_id,
        ))
        inserted += 1

    logger.info(
        "Fundamental ingestion selesai",
        symbol=instrument.canonical_symbol,
        provider=provider.name,
        inserted=inserted,
        skipped=skipped,
    )
    return inserted, skipped
