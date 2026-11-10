"""
Daily Intelligence route — R12 upgrade.

GET /daily  → DailyIntelligenceResponse

Briefing harian:
- Status bursa IDX + NYSE (calendar-aware, timezone-aware)
- Pergerakan harga tiap posisi vs hari sebelumnya (return 1D)
- Alert berstruktur dengan dedup (1 alert per kategori per instrumen)
- Gainers / losers count

Tidak memanggil LLM — semua deterministik dari data DB.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    DailyIntelligenceResponse,
    DailyPositionBrief,
    DigestAlertResponse,
    MarketSessionResponse,
)
from app.db.models import Instrument, PriceBar, Recommendation as RecommendationModel, Trade
from app.db.session import get_db
from app.domain.digest import build_digest
from app.portfolio.analyzer import LOSS_THRESHOLD, MAX_SINGLE_WEIGHT
from app.portfolio.calculator import compute_positions, enrich_positions_with_prices
from app.portfolio.seeder import get_or_create_default_portfolio

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/daily", tags=["daily"])

_STALE_DAYS = 3


@router.get("", response_model=DailyIntelligenceResponse)
async def get_daily_intelligence(
    db: AsyncSession = Depends(get_db),
) -> DailyIntelligenceResponse:
    """
    Briefing harian portfolio — calendar-aware, alert dedup, pergerakan 1D.
    """
    portfolio = await get_or_create_default_portfolio(db)
    trades_result = await db.execute(
        select(Trade).where(Trade.portfolio_id == portfolio.id)
    )
    trades = trades_result.scalars().all()
    positions = compute_positions(trades)

    now = datetime.now(tz=timezone.utc)
    today = now.date()

    if not positions:
        from app.domain.digest import get_market_sessions
        sessions = get_market_sessions(now)
        any_open = any(s.is_open_now for s in sessions)
        return DailyIntelligenceResponse(
            as_of=now,
            market_open=any_open,
            market_sessions=[
                MarketSessionResponse(
                    exchange=s.exchange,
                    is_trading_day=s.is_trading_day,
                    is_open_now=s.is_open_now,
                    local_time_str=s.local_time_str,
                    next_trading_day=s.next_trading_day,
                )
                for s in sessions
            ],
            total_positions=0,
            total_market_value=0.0,
            unrealized_pnl_pct=0.0,
            positions=[],
            alerts=["Portofolio kosong — tambahkan posisi pertama"],
            structured_alerts=[],
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

    # Ambil harga terkini + harga sebelumnya (2 bar terakhir per instrumen)
    prices: dict[str, tuple[float, object]] = {}       # untuk enrich_positions_with_prices
    price_data: dict[str, dict] = {}                   # untuk digest engine
    stale_count = 0

    for iid in positions:
        bars_result = await db.execute(
            select(PriceBar)
            .where(PriceBar.instrument_id == iid)
            .order_by(PriceBar.session_date.desc())
            .limit(2)
        )
        bars = list(bars_result.scalars().all())

        if bars:
            latest = bars[0]
            prev = bars[1] if len(bars) > 1 else None
            prices[iid] = (float(latest.close), latest.session_date)
            days_old = (today - latest.session_date).days
            if days_old > _STALE_DAYS:
                stale_count += 1

            price_data[iid] = {
                "today": float(latest.close),
                "prev": float(prev.close) if prev else None,
                "session_date": latest.session_date,
                "prev_date": prev.session_date if prev else None,
            }

    positions = enrich_positions_with_prices(positions, prices)

    # Ambil rekomendasi terbaru per instrumen
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
            rec_map[iid] = (rec.action, None)

    # Build digest (calendar + alert dedup + change stats)
    pos_dicts = [
        {
            "instrument_id": iid,
            "canonical_symbol": pos.canonical_symbol,
            "company_name": pos.company_name,
            "exchange": getattr(pos, "exchange", "IDX"),
            "weight": pos.weight,
            "unrealized_pnl_pct": pos.unrealized_pnl_pct,
        }
        for iid, pos in positions.items()
    ]
    digest = build_digest(
        as_of=now,
        positions=pos_dicts,
        price_data=price_data,
        max_position_weight=MAX_SINGLE_WEIGHT,
        loss_threshold=LOSS_THRESHOLD,
        stale_days=_STALE_DAYS,
    )

    # Build position briefs dengan return_1d dari digest
    change_map = {c.canonical_symbol: c for c in digest.position_changes}
    briefs: list[DailyPositionBrief] = []
    total_cost = sum(p.total_cost for p in positions.values())
    total_mv = sum(p.market_value for p in positions.values() if p.market_value is not None)
    total_pnl_pct = (total_mv - total_cost) / total_cost if total_cost > 0 and total_mv > 0 else 0.0

    for iid, pos in sorted(positions.items(), key=lambda x: -x[1].weight):
        action, urgency = rec_map.get(iid, (None, None))
        change = change_map.get(pos.canonical_symbol)
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
            return_1d=change.return_1d if change else None,
            prev_price=change.close_prev if change else None,
        ))

    # Backward-compat string alerts
    string_alerts = [a.message for a in digest.alerts]

    no_price_count = sum(1 for p in positions.values() if p.current_price is None)
    if no_price_count > 0:
        string_alerts.insert(0, f"{no_price_count} posisi tidak memiliki harga terkini")

    # Data freshness
    if stale_count == len(positions):
        freshness = "STALE"
    elif stale_count > 0 or no_price_count > 0:
        freshness = "PARTIAL"
    else:
        freshness = "FRESH"

    log.info(
        "daily.intelligence",
        positions=len(positions),
        alerts=len(digest.alerts),
        freshness=freshness,
        any_open=digest.any_market_open,
        gainers=digest.gainers_count,
        losers=digest.losers_count,
    )

    return DailyIntelligenceResponse(
        as_of=now,
        market_open=digest.any_market_open,
        market_sessions=[
            MarketSessionResponse(
                exchange=s.exchange,
                is_trading_day=s.is_trading_day,
                is_open_now=s.is_open_now,
                local_time_str=s.local_time_str,
                next_trading_day=s.next_trading_day,
            )
            for s in digest.market_sessions
        ],
        total_positions=len(positions),
        total_market_value=round(total_mv if total_mv > 0 else total_cost, 2),
        unrealized_pnl_pct=round(total_pnl_pct, 4),
        positions=briefs,
        alerts=string_alerts,
        structured_alerts=[
            DigestAlertResponse(
                category=a.category,
                symbol=a.symbol,
                message=a.message,
                severity=a.severity,
            )
            for a in digest.alerts
        ],
        data_freshness=freshness,
        gainers_count=digest.gainers_count,
        losers_count=digest.losers_count,
        unchanged_count=digest.unchanged_count,
    )
