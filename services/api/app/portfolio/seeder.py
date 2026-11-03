"""
Portfolio seeder — isi portofolio awal dari CR §10.
Idempotent: gunakan import_fingerprint untuk dedup.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Instrument, Portfolio, Trade

log = structlog.get_logger(__name__)

# Seed data dari CR §10
# Format: (canonical_symbol, lots, avg_price_per_share)
SEED_POSITIONS = [
    ("IDX:BMRI", 11, 4978.69),   # 11 lot × 100 saham = 1100 saham
    ("IDX:BBRI", 14, 2978.05),   # 14 lot × 100 saham = 1400 saham
    ("IDX:BBNI", 3,  3375.89),   # 3 lot × 100 saham = 300 saham
    ("IDX:BBCA", 1,  4978.69),   # 1 lot × 100 saham = 100 saham
]

SEED_DATE = date(2024, 1, 2)  # tanggal fiktif — data historis pre-aplikasi
LOT_SIZE = 100


async def get_or_create_default_portfolio(db: AsyncSession) -> Portfolio:
    """Ambil atau buat portfolio 'Default'."""
    result = await db.execute(select(Portfolio).where(Portfolio.name == "Default"))
    portfolio = result.scalar_one_or_none()

    if portfolio is None:
        portfolio = Portfolio(
            id=str(uuid.uuid4()),
            name="Default",
            base_currency="IDR",
            is_paper=False,
        )
        db.add(portfolio)
        await db.flush()
        log.info("portfolio.created", name="Default", id=portfolio.id)

    return portfolio


async def seed_initial_portfolio(db: AsyncSession) -> dict:
    """
    Seed portofolio awal dari CR §10.
    Idempotent — trade yang sudah ada (berdasarkan import_fingerprint) dilewati.
    Mengembalikan summary {created, skipped, errors}.
    """
    portfolio = await get_or_create_default_portfolio(db)

    results = {"created": 0, "skipped": 0, "errors": [], "portfolio_id": portfolio.id}

    for symbol, lots, avg_price in SEED_POSITIONS:
        fingerprint = f"SEED-{symbol.replace(':', '-')}-v1"

        # Cek apakah sudah ada
        existing = await db.execute(
            select(Trade).where(Trade.import_fingerprint == fingerprint)
        )
        if existing.scalar_one_or_none() is not None:
            log.debug("portfolio.seed.skip", symbol=symbol, reason="fingerprint_exists")
            results["skipped"] += 1
            continue

        # Cari instrumen
        instr_result = await db.execute(
            select(Instrument).where(Instrument.canonical_symbol == symbol)
        )
        instrument = instr_result.scalar_one_or_none()

        if instrument is None:
            log.warning("portfolio.seed.error", symbol=symbol, reason="instrument_not_found")
            results["errors"].append(f"Instrumen {symbol} tidak ditemukan — jalankan /admin/bootstrap lebih dulu")
            continue

        shares = float(lots * LOT_SIZE)
        trade = Trade(
            id=str(uuid.uuid4()),
            portfolio_id=portfolio.id,
            instrument_id=instrument.id,
            trade_date=SEED_DATE,
            side="BUY",
            shares=shares,
            price=avg_price,
            fee=0.0,
            tax=0.0,
            currency=instrument.currency,
            source_broker="SEED",
            import_fingerprint=fingerprint,
            notes=f"Data awal sesuai CR §10 — {lots} lot @{avg_price:,.2f}",
        )
        db.add(trade)
        results["created"] += 1
        log.info("portfolio.seed.created", symbol=symbol, lots=lots, price=avg_price)

    await db.flush()
    return results
