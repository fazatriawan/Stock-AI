"""
Performance route — Phase D.

GET /portfolio/performance  → Equity curve dan statistik return portofolio.
Dihitung deterministik dari trade history + price data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import EquityDataPoint, PerformanceResponse, PositionContribution
from app.db.models import Instrument, PriceBar, Trade
from app.db.session import get_db
from app.portfolio.calculator import compute_positions
from app.portfolio.seeder import get_or_create_default_portfolio

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/portfolio", tags=["performance"])

_RANGE_DAYS = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "2y": 730}


@router.get("/performance", response_model=PerformanceResponse)
async def get_portfolio_performance(
    range: str = Query("6m", description="1m, 3m, 6m, 1y, 2y"),
    db: AsyncSession = Depends(get_db),
) -> PerformanceResponse:
    """
    Equity curve portofolio berdasarkan trade history + harga historis.

    Metode: untuk setiap titik waktu, hitung market value dari posisi aktif
    pada saat itu berdasarkan harga close terdekat. Modal awal = total_cost
    dari semua BUY yang dilakukan hingga tanggal tersebut.
    """
    portfolio = await get_or_create_default_portfolio(db)
    days = _RANGE_DAYS.get(range, 180)
    today = date.today()
    start_date = today - timedelta(days=days)

    # Load semua trades
    trades_result = await db.execute(
        select(Trade)
        .where(Trade.portfolio_id == portfolio.id)
        .order_by(Trade.trade_date.asc())
    )
    all_trades = trades_result.scalars().all()

    if not all_trades:
        return PerformanceResponse(
            equity_curve=[],
            total_return_pct=0.0,
            total_invested=0.0,
            current_value=0.0,
            unrealized_pnl=0.0,
            best_position=None,
            worst_position=None,
            as_of=datetime.now(tz=timezone.utc),
        )

    # Load semua instrumen dari portfolio
    all_instrument_ids = list({t.instrument_id for t in all_trades})
    instr_result = await db.execute(
        select(Instrument).where(Instrument.id.in_(all_instrument_ids))
    )
    instruments = {i.id: i for i in instr_result.scalars().all()}

    # Load semua price bars dalam range
    price_result = await db.execute(
        select(PriceBar)
        .where(
            PriceBar.instrument_id.in_(all_instrument_ids),
            PriceBar.session_date >= start_date,
            PriceBar.session_date <= today,
        )
        .order_by(PriceBar.session_date.asc())
    )
    all_bars = price_result.scalars().all()

    # Buat price map: {instrument_id: {session_date: close}}
    price_map: dict[str, dict[date, float]] = {}
    for bar in all_bars:
        if bar.instrument_id not in price_map:
            price_map[bar.instrument_id] = {}
        price_map[bar.instrument_id][bar.session_date] = float(bar.close)

    def get_price_on_or_before(iid: str, d: date) -> Optional[float]:
        prices = price_map.get(iid, {})
        if not prices:
            return None
        # Cari harga pada atau sebelum tanggal d
        candidates = [p for dt, p in prices.items() if dt <= d]
        return candidates[-1] if candidates else None

    # Buat titik equity curve setiap 7 hari (atau lebih rapat untuk range pendek)
    step = 1 if days <= 30 else 7 if days <= 180 else 14
    equity_curve: list[EquityDataPoint] = []

    current = start_date
    while current <= today:
        # Hitung posisi aktif pada tanggal current
        trades_until = [t for t in all_trades if t.trade_date <= current]
        if not trades_until:
            current += timedelta(days=step)
            continue

        positions = compute_positions(trades_until)

        total_mv = 0.0
        total_cost = 0.0
        for iid, pos in positions.items():
            price = get_price_on_or_before(iid, current)
            mv = (price * pos.shares) if price else pos.total_cost
            total_mv += mv
            total_cost += pos.total_cost

        pnl_pct = (total_mv - total_cost) / total_cost if total_cost > 0 else 0.0

        equity_curve.append(EquityDataPoint(
            date=current,
            portfolio_value=round(total_mv, 0),
            invested=round(total_cost, 0),
            pnl_pct=round(pnl_pct * 100, 2),
        ))

        current += timedelta(days=step)

    # Hitung current state (hari ini)
    current_positions = compute_positions(all_trades)
    total_invested = sum(p.total_cost for p in current_positions.values())
    current_value = 0.0
    for iid, pos in current_positions.items():
        price = get_price_on_or_before(iid, today)
        current_value += (price * pos.shares) if price else pos.total_cost

    unrealized_pnl = current_value - total_invested
    total_return_pct = (unrealized_pnl / total_invested * 100) if total_invested > 0 else 0.0

    # Per-position contribution
    contributions: list[PositionContribution] = []
    for iid, pos in current_positions.items():
        instr = instruments.get(iid)
        price = get_price_on_or_before(iid, today)
        mv = (price * pos.shares) if price else pos.total_cost
        pnl = mv - pos.total_cost
        pnl_pct = pnl / pos.total_cost if pos.total_cost > 0 else 0.0
        contributions.append(PositionContribution(
            canonical_symbol=instr.canonical_symbol if instr else iid,
            company_name=instr.company_name if instr else None,
            total_cost=round(pos.total_cost, 0),
            current_value=round(mv, 0),
            unrealized_pnl=round(pnl, 0),
            unrealized_pnl_pct=round(pnl_pct * 100, 2),
            portfolio_weight=round(pos.weight * 100, 1),
        ))

    contributions.sort(key=lambda c: c.unrealized_pnl_pct, reverse=True)
    best = contributions[0] if contributions else None
    worst = contributions[-1] if contributions else None

    return PerformanceResponse(
        equity_curve=equity_curve,
        total_return_pct=round(total_return_pct, 2),
        total_invested=round(total_invested, 0),
        current_value=round(current_value, 0),
        unrealized_pnl=round(unrealized_pnl, 0),
        position_contributions=contributions,
        best_position=best,
        worst_position=worst,
        as_of=datetime.now(tz=timezone.utc),
    )
