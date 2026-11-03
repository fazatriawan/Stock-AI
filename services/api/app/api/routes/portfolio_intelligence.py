"""
Portfolio Intelligence routes — Phase 3.

GET /portfolio/health         → PortfolioHealthResponse (skor, konsentrasi, diversifikasi)
GET /portfolio/loss           → LossAnalyzerResponse (posisi rugi + 5 skenario)
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ConcentrationRiskResponse,
    LossAnalyzerResponse,
    LossPositionResponse,
    LossScenarioResponse,
    PortfolioHealthResponse,
    SectorRiskResponse,
)
from app.db.models import Instrument, Portfolio, PriceBar, Trade
from app.db.session import get_db
from app.portfolio.analyzer import (
    analyze_loss_position,
    compute_portfolio_health,
)
from app.portfolio.calculator import (
    PositionData,
    compute_positions,
    enrich_positions_with_prices,
)
from app.portfolio.seeder import get_or_create_default_portfolio

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio-intelligence"])


async def _load_positions_with_prices(
    db: AsyncSession,
) -> tuple[dict[str, PositionData], dict[str, float], Portfolio]:
    """
    Helper: load portfolio + trade + harga terkini, kembalikan positions yang sudah enriched.
    """
    portfolio = await get_or_create_default_portfolio(db)

    trades_result = await db.execute(
        select(Trade).where(Trade.portfolio_id == portfolio.id)
    )
    trades = trades_result.scalars().all()

    positions = compute_positions(trades)
    if not positions:
        return positions, {}, portfolio

    # Enrich dengan info instrumen
    if positions:
        instr_result = await db.execute(
            select(Instrument).where(
                Instrument.id.in_(list(positions.keys()))
            )
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

    # Ambil harga terkini dari PriceBar
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

    positions = enrich_positions_with_prices(positions, prices)

    # Hitung sector weights
    sector_weights: dict[str, float] = {}
    for pos in positions.values():
        if pos.sector and pos.weight > 0:
            sector_weights[pos.sector] = sector_weights.get(pos.sector, 0.0) + pos.weight

    return positions, sector_weights, portfolio


@router.get("/health", response_model=PortfolioHealthResponse)
async def get_portfolio_health(
    db: AsyncSession = Depends(get_db),
) -> PortfolioHealthResponse:
    """
    Analisis kesehatan portofolio: skor 0–100, konsentrasi, diversifikasi, rekomendasi.
    """
    positions, sector_weights, portfolio = await _load_positions_with_prices(db)

    report = compute_portfolio_health(positions, sector_weights)

    return PortfolioHealthResponse(
        health_score=report.health_score,
        grade=report.grade.value,
        position_count=report.position_count,
        diversification_score=report.diversification_score,
        concentration_risks=[
            ConcentrationRiskResponse(
                symbol=r.symbol,
                weight=r.weight,
                severity=r.severity,
                message=r.message,
            )
            for r in report.concentration_risks
        ],
        sector_risks=[
            SectorRiskResponse(
                sector=r.sector,
                weight=r.weight,
                severity=r.severity,
                message=r.message,
            )
            for r in report.sector_risks
        ],
        largest_position_symbol=report.largest_position_symbol,
        largest_position_weight=report.largest_position_weight,
        total_invested=report.total_invested,
        total_market_value=report.total_market_value,
        unrealized_pnl=report.unrealized_pnl,
        unrealized_pnl_pct=report.unrealized_pnl_pct,
        diversification_component=report.diversification_component,
        concentration_component=report.concentration_component,
        pnl_component=report.pnl_component,
        warnings=report.warnings,
        recommendations=report.recommendations,
    )


@router.get("/loss", response_model=LossAnalyzerResponse)
async def get_loss_analysis(
    db: AsyncSession = Depends(get_db),
) -> LossAnalyzerResponse:
    """
    Analisis semua posisi yang sedang rugi dengan 5 skenario aksi.

    Hanya posisi dengan unrealized P/L < −5% yang masuk analisis.
    Skenario: Cut Loss, Partial Cut, Hold, Average Down, Stop Loss.
    """
    positions, sector_weights, portfolio = await _load_positions_with_prices(db)

    loss_positions: list[LossPositionResponse] = []
    total_loss = 0.0

    for pos in positions.values():
        analysis = analyze_loss_position(pos)
        if analysis is None:
            continue

        total_loss += analysis.unrealized_pnl

        loss_positions.append(LossPositionResponse(
            canonical_symbol=analysis.canonical_symbol,
            company_name=analysis.company_name,
            shares=analysis.shares,
            lots=analysis.lots,
            avg_cost=analysis.avg_cost,
            current_price=analysis.current_price,
            total_cost=analysis.total_cost,
            market_value=analysis.market_value,
            unrealized_pnl=analysis.unrealized_pnl,
            unrealized_pnl_pct=analysis.unrealized_pnl_pct,
            scenarios=[
                LossScenarioResponse(
                    scenario=s.scenario.value,
                    label=s.label,
                    description=s.description,
                    projected_loss_idr=s.projected_loss_idr,
                    projected_loss_pct=s.projected_loss_pct,
                    remaining_exposure_idr=s.remaining_exposure_idr,
                    breakeven_price=s.breakeven_price,
                    pros=s.pros,
                    cons=s.cons,
                    risk_level=s.risk_level,
                )
                for s in analysis.scenarios
            ],
            suggested_scenario=analysis.suggested_scenario.value,
            suggested_reason=analysis.suggested_reason,
        ))

    # Sortir: rugi terbesar (paling negatif) di atas
    loss_positions.sort(key=lambda p: p.unrealized_pnl)

    log.info(
        "portfolio.loss_analysis",
        loss_count=len(loss_positions),
        total_loss=total_loss,
    )

    return LossAnalyzerResponse(
        loss_positions=loss_positions,
        total_loss_positions=len(loss_positions),
        total_unrealized_loss_idr=round(total_loss, 2),
        as_of=datetime.now(tz=timezone.utc),
    )
