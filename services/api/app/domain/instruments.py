"""
Canonical instrument registry dan ticker resolution.
IDX:BMRI, BMRI, BMRI.JK → instrument yang sama.
"""
from __future__ import annotations

import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Instrument, InstrumentAlias
from app.providers.base import InstrumentInfo


# Normalisasi alias yang diketahui
def normalize_symbol(raw: str) -> str:
    """Bersihkan input ticker: uppercase, hapus whitespace, strip .JK suffix."""
    s = raw.strip().upper()
    if s.endswith(".JK"):
        s = s[:-3]
    return s


def guess_exchange(symbol: str) -> str | None:
    """Heuristik exchange dari format symbol."""
    if re.match(r"^[A-Z]{2,6}\.JK$", symbol, re.IGNORECASE):
        return "IDX"
    if re.match(r"^IDX:[A-Z]{2,6}$", symbol, re.IGNORECASE):
        return "IDX"
    if re.match(r"^US:[A-Z]{1,5}(\.[A-Z])?$", symbol, re.IGNORECASE):
        return "US"
    return None


async def resolve_instrument(
    db: AsyncSession,
    query: str,
) -> Instrument | None:
    """
    Cari instrument dari berbagai format query:
    - canonical_symbol: IDX:BMRI
    - local_symbol: BMRI
    - alias: BMRI.JK
    """
    q = normalize_symbol(query)

    # 1. Cari by canonical_symbol langsung
    result = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == q)
    )
    instrument = result.scalar_one_or_none()
    if instrument:
        return instrument

    # 2. Cari by canonical_symbol dengan prefix IDX:
    result = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == f"IDX:{q}")
    )
    instrument = result.scalar_one_or_none()
    if instrument:
        return instrument

    # 3. Cari by canonical_symbol dengan prefix US:
    result = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == f"US:{q}")
    )
    instrument = result.scalar_one_or_none()
    if instrument:
        return instrument

    # 4. Cari by local_symbol
    result = await db.execute(
        select(Instrument).where(Instrument.local_symbol == q)
    )
    instrument = result.scalar_one_or_none()
    if instrument:
        return instrument

    # 5. Cari by alias
    alias_result = await db.execute(
        select(InstrumentAlias).where(InstrumentAlias.alias == q)
    )
    alias = alias_result.scalar_one_or_none()
    if alias:
        result2 = await db.execute(
            select(Instrument).where(Instrument.id == alias.instrument_id)
        )
        return result2.scalar_one_or_none()

    return None


async def search_instruments(
    db: AsyncSession,
    query: str,
    limit: int = 20,
) -> list[Instrument]:
    """Full-text search sederhana pada canonical_symbol, local_symbol, company_name."""
    q = f"%{query.strip().upper()}%"
    result = await db.execute(
        select(Instrument)
        .where(
            (Instrument.canonical_symbol.ilike(q)) |
            (Instrument.local_symbol.ilike(q)) |
            (Instrument.company_name.ilike(q))
        )
        .where(Instrument.status == "ACTIVE")
        .limit(limit)
    )
    return list(result.scalars().all())


async def upsert_instrument(
    db: AsyncSession,
    info: InstrumentInfo,
) -> Instrument:
    """Buat atau update instrument dari provider info."""
    result = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == info.canonical_symbol)
    )
    instrument = result.scalar_one_or_none()

    if instrument is None:
        instrument = Instrument(
            canonical_symbol=info.canonical_symbol,
            local_symbol=info.local_symbol,
            exchange=info.exchange,
            mic=info.mic,
            country=info.country,
            currency=info.currency,
            timezone=info.timezone,
            asset_type=info.asset_type,
            sector=info.sector,
            industry=info.industry,
            company_name=info.company_name,
            status="ACTIVE",
        )
        db.add(instrument)
    else:
        # Update field yang boleh berubah
        instrument.sector = info.sector or instrument.sector
        instrument.industry = info.industry or instrument.industry
        instrument.company_name = info.company_name or instrument.company_name
        instrument.status = "ACTIVE"

    await db.flush()
    return instrument
