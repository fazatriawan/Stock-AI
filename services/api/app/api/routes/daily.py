"""
Daily Intelligence route — Phase 5.

GET /daily  → DailyIntelligenceResponse

Briefing harian singkat: posisi saat ini, P/L, alert konsentrasi/loss.
Tidak memanggil LLM — semua deterministik dari data DB.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DailyIntelligenceResponse, DailyPositionBrief
from app.db.models import Instrument, PriceBar, Recommendation as RecommendationModel, Trade
from app.db.session import get_db
from app.portfolio.calculator import compute_positions, enrich_positions_with_prices
from app.portfolio.analyzer import LOSS_THRESHOLD, MAX_SINGLE_WEIGHT
from app.portfolio.seeder import get_or_create_default_portfolio

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/daily", tags=["daily"])

_STALE_DAYS = 3


@router.get("", response_model=DailyIntelligenceResponse)
async def get_daily_intelligence(
    db: AsyncSession = Depends(get_db),
) -> DailyIntelligenceResponse:
    """
    Briefing harian portfolio:
    - Semua posisi dengan harga terkini dan P/L
    - Alert konsentrasi dan posisi rugi signifikan
    - Status data freshness
    """
    portfolio = await get_or_create_default_portfolio(db)
    trades_result = await db.execute(
        select(Trade).where(Trade.portfolio_id == portfolio.id)
    )
    trades = trades_result.scalars().all()
    positions = compute_positions(trades)

    if not positions:
        return DailyIntelligenceResponse(
            as_of=datetime.now(tz=timezone.utc),
            market_open=False,
            total_positions=0,
            total_market_value=0.0,
            unrealized_pnl_pct=0.0,
            positions=[],
            alerts=["Portofolio kosong — tambahkan posisi pertama"],
            data_freshness="FRESH",
        )

    # Enrich instrumen
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

    # Ambil harga terkini
    prices: dict[str, tuple[float, object]] = {}
    from datetime import date, timedelta
    today = date.today()
    stale_count = 0

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
            days_old = (today - bar.session_date).days
            if days_old > _STALE_DAYS:
                stale_count += 1

    positions = enrich_positions_with_prices(positions, prices)

    # Ambil rekomendasi terbaru per instrumen (jika ada)
    rec_map: dict[str, tuple[str, str | None]] = {}
    for iid in positions:
        rec_result = await db.execute(
            select(RecommendationModel)
            .where(RecommendationModel.instrument_id == iid)
            .order_by(RecommendationModel.created_at.desc())
            .limit(1)
        )
        rec = rec_result.scalar_one_or_none()
        if rec:
            rec_map[iid] = (rec.action, None)  # urgency tidak ada di DB model saat ini

    # Build position briefs
    briefs: list[DailyPositionBrief] = []
    total_cost = sum(p.total_cost for p in positions.values())
    total_mv = sum(p.market_value for p in positions.values() if p.market_value is not None)
    total_pnl_pct = (total_mv - total_cost) / total_cost if total_cost > 0 and total_mv > 0 else 0.0

    for iid, pos in sorted(positions.items(), key=lambda x: -x[1].weight):
        action, urgency = rec_map.get(iid, (None, None))
        briefs.append(DailyPositionBrief(
            canonical_symbol=pos.canonical_symbol,
            company_name=pos.company_name,
            lots=pos.lots,
            avg_cost=pos.avg_cost,
            current_price=pos.current_price,
            unrealized_pnl_pct=pos.unrealized_pnl_pct,
            weight=pos.weight,
            action=action,
            urgency=urgency,
            data_stale=iid not in prices,
        ))

    # Build alerts
    alerts: list[str] = []
    for pos in positions.values():
        if pos.weight >= MAX_SINGLE_WEIGHT:
            alerts.append(f"{pos.canonical_symbol.split(':')[-1]} {pos.weight*100:.0f}% — overweight, pertimbangkan trim")
        if pos.unrealized_pnl_pct is not None and pos.unrealized_pnl_pct < LOSS_THRESHOLD:
            alerts.append(f"{pos.canonical_symbol.split(':')[-1]} rugi {abs(pos.unrealized_pnl_pct)*100:.1f}% — lihat Loss Analyzer")

    no_price_count = sum(1 for p in positions.values() if p.current_price is None)
    if no_price_count > 0:
        alerts.append(f"{no_price_count} posisi tidak memiliki harga terkini")

    # Data freshness
    if stale_count == len(positions):
        freshness = "STALE"
    elif stale_count > 0 or no_price_count > 0:
        freshness = "PARTIAL"
    else:
        freshness = "FRESH"

    log.info("daily.intelligence", positions=len(positions), alerts=len(alerts), freshness=freshness)

    return DailyIntelligenceResponse(
        as_of=datetime.now(tz=timezone.utc),
        market_open=False,  # TODO: integrasikan dengan MarketSession
        total_positions=len(positions),
        total_market_value=round(total_mv if total_mv > 0 else total_cost, 2),
        unrealized_pnl_pct=round(total_pnl_pct, 4),
        positions=briefs,
        alerts=alerts,
        data_freshness=freshness,
    )
