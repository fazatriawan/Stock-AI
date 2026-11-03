"""
Rebalance simulator routes — Phase 4.

POST /portfolio/simulate/rebalance   → RebalanceSimulationResponse
POST /portfolio/simulate/allocate    → CapitalAllocationResponse

Semua simulasi bersifat hipotetis — tidak ada transaksi nyata.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AllocationSuggestionResponse,
    CapitalAllocationRequest,
    CapitalAllocationResponse,
    RebalanceRequest,
    RebalanceSimulationResponse,
    TargetAllocationResponse,
)
from app.db.models import Instrument, PriceBar, Trade
from app.db.session import get_db
from app.portfolio.calculator import compute_positions, enrich_positions_with_prices
from app.portfolio.seeder import get_or_create_default_portfolio
from app.portfolio.simulator import plan_new_capital, simulate_rebalance

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/portfolio/simulate", tags=["portfolio-simulator"])


async def _load_enriched_positions(db: AsyncSession):
    """Helper: load dan enrich positions dengan harga terkini."""
    portfolio = await get_or_create_default_portfolio(db)
    trades_result = await db.execute(
        select(Trade).where(Trade.portfolio_id == portfolio.id)
    )
    trades = trades_result.scalars().all()
    positions = compute_positions(trades)

    if not positions:
        return positions

    instr_result = await db.execute(
        select(Instrument).where(Instrument.id.in_(list(positions.keys())))
    )
    instruments = {i.id: i for i in instr_result.scalars().all()}
    for iid, pos in positions.items():
        if iid in instruments:
            instr = instruments[iid]
            pos.canonical_symbol = instr.canonical_symbol
            pos.company_name = instr.company_name
            pos.exchange = instr.exchange
            pos.currency = instr.currency
            pos.sector = instr.sector

    prices: dict[str, tuple[float, object]] = {}
    for iid in positions:
        price_result = await db.execute(
            select(PriceBar)
            .where(PriceBar.instrument_id == iid)
            .order_by(PriceBar.session_date.desc())
            .limit(1)
        )
        bar = price_result.scalar_one_or_none()
        if bar:
            prices[iid] = (float(bar.close), bar.session_date)

    return enrich_positions_with_prices(positions, prices)


@router.post("/rebalance", response_model=RebalanceSimulationResponse)
async def simulate_rebalance_route(
    body: RebalanceRequest,
    db: AsyncSession = Depends(get_db),
) -> RebalanceSimulationResponse:
    """
    Simulasi rebalancing ke target bobot.

    Jika target_weights kosong, simulasi equal-weight (1/n per posisi).
    new_capital menambahkan modal baru ke total sebelum menghitung delta.

    Tidak ada transaksi yang dieksekusi — hanya simulasi.
    """
    positions = await _load_enriched_positions(db)

    if not positions:
        raise HTTPException(status_code=404, detail="Portofolio kosong — tambahkan posisi terlebih dahulu")

    # Jika tidak ada target weights, gunakan equal weight
    target_weights = dict(body.target_weights)
    if not target_weights:
        n = len(positions)
        eq = 1.0 / n
        for pos in positions.values():
            target_weights[pos.canonical_symbol] = eq

    result = simulate_rebalance(positions, target_weights, body.new_capital)

    log.info(
        "portfolio.simulate_rebalance",
        positions=result.positions_count,
        buy=result.buy_actions,
        sell=result.sell_actions,
        net_cash=result.net_cash_needed,
    )

    return RebalanceSimulationResponse(
        total_portfolio_value=result.total_portfolio_value,
        positions_count=result.positions_count,
        allocations=[
            TargetAllocationResponse(
                canonical_symbol=a.canonical_symbol,
                company_name=a.company_name,
                sector=a.sector,
                current_lots=a.current_lots,
                current_weight=a.current_weight,
                target_weight=a.target_weight,
                current_market_value=a.current_market_value,
                target_market_value=a.target_market_value,
                delta_value=a.delta_value,
                delta_lots=a.delta_lots,
                action=a.action,
                note=a.note,
            )
            for a in result.allocations
        ],
        buy_actions=result.buy_actions,
        sell_actions=result.sell_actions,
        hold_actions=result.hold_actions,
        total_buy_value=result.total_buy_value,
        total_sell_value=result.total_sell_value,
        net_cash_needed=result.net_cash_needed,
        disclaimer=result.disclaimer,
    )


@router.post("/allocate", response_model=CapitalAllocationResponse)
async def plan_capital_allocation(
    body: CapitalAllocationRequest,
    db: AsyncSession = Depends(get_db),
) -> CapitalAllocationResponse:
    """
    Sarankan alokasi modal baru ke posisi yang underweight.

    Prioritaskan posisi yang paling underweight dari equal-weight ideal.
    Tidak ada transaksi — hanya rencana.
    """
    if body.new_capital <= 0:
        raise HTTPException(status_code=422, detail="new_capital harus positif")

    positions = await _load_enriched_positions(db)
    if not positions:
        raise HTTPException(status_code=404, detail="Portofolio kosong")

    result = plan_new_capital(positions, body.new_capital)

    return CapitalAllocationResponse(
        new_capital=result.new_capital,
        total_positions=result.total_positions,
        suggestions=[
            AllocationSuggestionResponse(
                canonical_symbol=s.canonical_symbol,
                company_name=s.company_name,
                sector=s.sector,
                current_weight=s.current_weight,
                suggested_new_amount=s.suggested_new_amount,
                suggested_lots=s.suggested_lots,
                rationale=s.rationale,
                priority=s.priority,
            )
            for s in result.suggestions
        ],
        undiversified_warning=result.undiversified_warning,
        disclaimer=result.disclaimer,
    )
