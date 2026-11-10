"""
R14 — Loader transaksi insider dari DB.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.insider import InsiderSignal, InsiderTxSummary, analyze_insider_signal
from app.db.models import Instrument, InsiderTransaction


async def load_insider_signal(
    db: AsyncSession,
    instrument: Instrument,
    as_of: date,
    lookback_days: int = 180,
) -> InsiderSignal:
    """Load semua transaksi insider dari DB lalu hitung sinyal."""
    result = await db.execute(
        select(InsiderTransaction)
        .where(InsiderTransaction.instrument_id == instrument.id)
        .order_by(InsiderTransaction.transaction_date.desc())
    )
    rows = list(result.scalars().all())

    summaries = [
        InsiderTxSummary(
            insider_name=r.insider_name,
            insider_role=r.insider_role,
            transaction_type=r.transaction_type,
            transaction_date=r.transaction_date,
            shares=r.shares,
            price_per_share=float(r.price_per_share) if r.price_per_share else None,
            total_value=float(r.total_value) if r.total_value else None,
            currency=r.currency,
            shares_owned_after=r.shares_owned_after,
            ownership_pct_after=float(r.ownership_pct_after) if r.ownership_pct_after else None,
            disclosure_date=r.disclosure_date,
            source_url=r.source_url,
        )
        for r in rows
    ]

    return analyze_insider_signal(summaries, as_of=as_of, lookback_days=lookback_days)


async def upsert_insider_transaction(
    db: AsyncSession,
    instrument: Instrument,
    data: dict,
) -> bool:
    """Insert atau skip jika sudah ada (kompatibel dengan PostgreSQL dan SQLite)."""
    existing_res = await db.execute(
        select(InsiderTransaction.id).where(
            InsiderTransaction.instrument_id == instrument.id,
            InsiderTransaction.insider_name == data["insider_name"],
            InsiderTransaction.transaction_date == data["transaction_date"],
            InsiderTransaction.transaction_type == data["transaction_type"],
            InsiderTransaction.shares == data["shares"],
        )
    )
    if existing_res.scalar_one_or_none() is not None:
        return False

    tx = InsiderTransaction(
        instrument_id=instrument.id,
        insider_name=data["insider_name"],
        insider_role=data["insider_role"],
        transaction_type=data["transaction_type"],
        transaction_date=data["transaction_date"],
        shares=data["shares"],
        price_per_share=data.get("price_per_share"),
        total_value=data.get("total_value"),
        currency=data.get("currency", "IDR"),
        shares_owned_after=data.get("shares_owned_after"),
        ownership_pct_after=data.get("ownership_pct_after"),
        disclosure_date=data.get("disclosure_date"),
        source_url=data.get("source_url"),
        notes=data.get("notes"),
    )
    db.add(tx)
    await db.flush()
    return True
