"""
Portfolio routes — Phase 1 Foundation.
Semua transaksi hanya manual oleh user — tidak ada auto-trading.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import (
    PortfolioSeedResponse,
    PortfolioSummaryResponse,
    PositionResponse,
    TradeCreateRequest,
    TradeResponse,
)
from app.db.models import Instrument, Portfolio, PriceBar, Trade
from app.db.session import get_db
from app.portfolio.calculator import compute_positions, enrich_positions_with_prices
from app.portfolio.seeder import get_or_create_default_portfolio, seed_initial_portfolio

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_latest_prices(
    instrument_ids: list[str],
    db: AsyncSession,
) -> dict[str, tuple[float, date]]:
    """Ambil harga terakhir untuk sekumpulan instrument_id dari price_bars."""
    if not instrument_ids:
        return {}

    prices: dict[str, tuple[float, date]] = {}

    for iid in instrument_ids:
        result = await db.execute(
            select(PriceBar)
            .where(PriceBar.instrument_id == iid)
            .order_by(PriceBar.session_date.desc())
            .limit(1)
        )
        bar = result.scalar_one_or_none()
        if bar is not None:
            prices[iid] = (float(bar.close), bar.session_date)

    return prices


async def _get_instruments(
    instrument_ids: list[str],
    db: AsyncSession,
) -> dict[str, Instrument]:
    result = await db.execute(
        select(Instrument).where(Instrument.id.in_(instrument_ids))
    )
    return {inst.id: inst for inst in result.scalars().all()}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary(db: AsyncSession = Depends(get_db)) -> PortfolioSummaryResponse:
    """
    Ambil ringkasan portofolio dengan posisi aktif, harga pasar, dan P/L tidak terealisasi.
    """
    portfolio = await get_or_create_default_portfolio(db)

    # Load semua trade untuk portfolio ini
    trades_result = await db.execute(
        select(Trade)
        .where(Trade.portfolio_id == portfolio.id)
        .order_by(Trade.trade_date)
    )
    trades = list(trades_result.scalars().all())

    if not trades:
        return PortfolioSummaryResponse(
            portfolio_id=portfolio.id,
            portfolio_name=portfolio.name,
            base_currency=portfolio.base_currency,
            as_of=datetime.now(timezone.utc),
            total_invested=0.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            positions=[],
            sector_weights={},
            concentration_warnings=[],
            trade_count=0,
        )

    # Hitung posisi dari trade history (WAC)
    raw_positions = compute_positions(trades)

    if not raw_positions:
        return PortfolioSummaryResponse(
            portfolio_id=portfolio.id,
            portfolio_name=portfolio.name,
            base_currency=portfolio.base_currency,
            as_of=datetime.now(timezone.utc),
            total_invested=0.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            positions=[],
            sector_weights={},
            concentration_warnings=[],
            trade_count=len(trades),
        )

    # Ambil instrument metadata
    instrument_ids = list(raw_positions.keys())
    instruments_map = await _get_instruments(instrument_ids, db)
    prices_map = await _get_latest_prices(instrument_ids, db)

    # Enrich posisi dengan metadata instrument
    for iid, pos in raw_positions.items():
        inst = instruments_map.get(iid)
        if inst:
            pos.canonical_symbol = inst.canonical_symbol
            pos.company_name = inst.company_name
            pos.exchange = inst.exchange
            pos.currency = inst.currency
            pos.sector = inst.sector

    # Enrich dengan harga pasar dan hitung P/L
    raw_positions = enrich_positions_with_prices(raw_positions, prices_map)

    # Hitung total portfolio
    total_market_value = sum(
        p.market_value for p in raw_positions.values() if p.market_value is not None
    )
    total_invested = sum(p.total_cost for p in raw_positions.values())
    unrealized_pnl = total_market_value - total_invested
    unrealized_pnl_pct = (unrealized_pnl / total_invested) if total_invested > 0 else 0.0

    # Sector weights
    sector_weights: dict[str, float] = {}
    for pos in raw_positions.values():
        if pos.sector and total_market_value > 0:
            mv = pos.market_value or (pos.total_cost)
            sector_weights[pos.sector] = sector_weights.get(pos.sector, 0.0) + mv / total_market_value

    # Concentration warnings
    warnings = []
    for sector, w in sector_weights.items():
        if w > 0.50:
            warnings.append(f"Konsentrasi tinggi di sektor {sector}: {w:.0%} dari portofolio")
    for pos in raw_positions.values():
        if pos.weight > 0.25:
            warnings.append(f"{pos.canonical_symbol or pos.instrument_id}: {pos.weight:.0%} melebihi batas 25% per saham")

    # Convert ke response model
    positions_resp = [
        PositionResponse(
            instrument_id=pos.instrument_id,
            canonical_symbol=pos.canonical_symbol,
            company_name=pos.company_name,
            exchange=pos.exchange,
            currency=pos.currency,
            sector=pos.sector,
            shares=pos.shares,
            lots=pos.lots,
            avg_cost=pos.avg_cost,
            total_cost=round(pos.total_cost, 2),
            current_price=pos.current_price,
            current_price_date=pos.current_price_date,
            market_value=pos.market_value,
            unrealized_pnl=pos.unrealized_pnl,
            unrealized_pnl_pct=pos.unrealized_pnl_pct,
            weight=pos.weight,
            trade_count=pos.trade_count,
            first_buy_date=pos.first_buy_date,
            last_trade_date=pos.last_trade_date,
        )
        for pos in sorted(raw_positions.values(), key=lambda p: -(p.market_value or p.total_cost))
    ]

    return PortfolioSummaryResponse(
        portfolio_id=portfolio.id,
        portfolio_name=portfolio.name,
        base_currency=portfolio.base_currency,
        as_of=datetime.now(timezone.utc),
        total_invested=round(total_invested, 2),
        market_value=round(total_market_value, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        unrealized_pnl_pct=round(unrealized_pnl_pct, 4),
        positions=positions_resp,
        sector_weights={k: round(v, 4) for k, v in sector_weights.items()},
        concentration_warnings=warnings,
        trade_count=len(trades),
    )


@router.get("/trades", response_model=list[TradeResponse])
async def list_trades(db: AsyncSession = Depends(get_db)) -> list[TradeResponse]:
    """Daftar semua trade di portofolio default."""
    portfolio = await get_or_create_default_portfolio(db)

    result = await db.execute(
        select(Trade, Instrument)
        .join(Instrument, Trade.instrument_id == Instrument.id)
        .where(Trade.portfolio_id == portfolio.id)
        .order_by(Trade.trade_date.desc(), Trade.id.desc())
    )
    rows = result.all()

    return [
        TradeResponse(
            id=t.id,
            portfolio_id=t.portfolio_id,
            instrument_id=t.instrument_id,
            canonical_symbol=inst.canonical_symbol,
            company_name=inst.company_name,
            trade_date=t.trade_date,
            side=t.side,
            shares=float(t.shares),
            lots=round(float(t.shares) / 100, 2),
            price=float(t.price),
            fee=float(t.fee or 0),
            tax=float(t.tax or 0),
            currency=t.currency,
            source_broker=t.source_broker,
            notes=t.notes,
            created_at=t.created_at,
        )
        for t, inst in rows
    ]


@router.post("/trades", response_model=TradeResponse, status_code=201)
async def add_trade(
    body: TradeCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> TradeResponse:
    """
    Tambah transaksi manual.
    Semua keputusan transaksi sepenuhnya menjadi tanggung jawab pengguna.
    """
    portfolio = await get_or_create_default_portfolio(db)

    # Resolve instrument
    result = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == body.canonical_symbol)
    )
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrumen {body.canonical_symbol!r} tidak ditemukan")

    if body.side not in ("BUY", "SELL"):
        raise HTTPException(status_code=422, detail="side harus BUY atau SELL")

    if body.shares <= 0 or body.price <= 0:
        raise HTTPException(status_code=422, detail="shares dan price harus positif")

    # Generate fingerprint unik untuk dedup
    fingerprint = f"MANUAL-{portfolio.id}-{instrument.id}-{body.trade_date}-{body.side}-{body.shares}-{uuid.uuid4().hex[:8]}"

    trade = Trade(
        id=str(uuid.uuid4()),
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        trade_date=body.trade_date,
        side=body.side,
        shares=body.shares,
        price=body.price,
        fee=body.fee or 0.0,
        tax=body.tax or 0.0,
        currency=body.currency or instrument.currency,
        source_broker=body.source_broker,
        import_fingerprint=fingerprint,
        notes=body.notes,
    )
    db.add(trade)
    await db.flush()

    log.info(
        "portfolio.trade.added",
        symbol=body.canonical_symbol,
        side=body.side,
        shares=body.shares,
        price=body.price,
    )

    return TradeResponse(
        id=trade.id,
        portfolio_id=trade.portfolio_id,
        instrument_id=trade.instrument_id,
        canonical_symbol=instrument.canonical_symbol,
        company_name=instrument.company_name,
        trade_date=trade.trade_date,
        side=trade.side,
        shares=float(trade.shares),
        lots=round(float(trade.shares) / 100, 2),
        price=float(trade.price),
        fee=float(trade.fee or 0),
        tax=float(trade.tax or 0),
        currency=trade.currency,
        source_broker=trade.source_broker,
        notes=trade.notes,
        created_at=trade.created_at,
    )


@router.delete("/trades/{trade_id}", status_code=204)
async def delete_trade(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Hapus transaksi. Hanya trade MANUAL yang boleh dihapus (bukan SEED)."""
    portfolio = await get_or_create_default_portfolio(db)

    result = await db.execute(
        select(Trade).where(
            Trade.id == trade_id,
            Trade.portfolio_id == portfolio.id,
        )
    )
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")

    # Proteksi: jangan hapus seed data (bisa merusak posisi awal)
    if trade.import_fingerprint and trade.import_fingerprint.startswith("SEED-"):
        raise HTTPException(
            status_code=403,
            detail="Trade seed tidak dapat dihapus. Tambahkan trade koreksi jika perlu.",
        )

    await db.delete(trade)
    log.info("portfolio.trade.deleted", trade_id=trade_id)


@router.post("/seed", response_model=PortfolioSeedResponse)
async def seed_portfolio(db: AsyncSession = Depends(get_db)) -> PortfolioSeedResponse:
    """
    Isi portofolio awal dari data CR §10.
    Idempotent — aman dijalankan berkali-kali.
    Instrumen harus sudah ada (jalankan /admin/bootstrap lebih dulu).
    """
    result = await seed_initial_portfolio(db)
    return PortfolioSeedResponse(
        message="Seed selesai",
        portfolio_id=result["portfolio_id"],
        created=result["created"],
        skipped=result["skipped"],
        errors=result["errors"],
    )
