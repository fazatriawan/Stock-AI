"""
R22 — Dashboard Summary endpoint.

GET /summary  → Aggregasi sinyal macro + swing setups + recent alerts + watchlist near target.
Endpoint ini read-only, dirancang untuk panel utama daily dashboard.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.swing import SetupType, detect_swing_setup
from app.api.schemas import (
    DashboardSummaryResponse,
    SummaryAlertItem,
    SummaryMacroBlock,
    SummarySwingItem,
    SummaryWatchItem,
)
from app.db.models import Alert, Instrument, PriceBar, WatchlistItem
from app.db.session import get_db

import pandas as pd

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/summary", tags=["summary"])

_PRICE_DAYS = 60
_SWING_SAMPLE = 20   # max instrumen untuk di-screen swing (hanya yang aktif)
_ALERT_HISTORY = 10
_NEAR_TARGET_PCT = 10.0  # watchlist items yang price ≤ 10% dari target


async def _load_df(instrument_id: str, db: AsyncSession) -> pd.DataFrame:
    end   = date.today()
    start = end - timedelta(days=_PRICE_DAYS)
    result = await db.execute(
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument_id,
               PriceBar.session_date.between(start, end))
        .order_by(PriceBar.session_date.asc())
    )
    bars = result.scalars().all()
    if not bars:
        return pd.DataFrame()
    return pd.DataFrame([{
        "session_date": b.session_date,
        "open":   float(b.open)   if b.open  else None,
        "high":   float(b.high)   if b.high  else float(b.close),
        "low":    float(b.low)    if b.low   else float(b.close),
        "close":  float(b.close),
        "volume": b.volume or 0,
    } for b in bars])


@router.get("", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    swing_limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummaryResponse:
    """
    Ringkasan daily dashboard:
    - Sinyal macro (yield curve, fed rate, impact score)
    - Top swing setups
    - Recent alerts (10 terakhir)
    - Watchlist items yang mendekati price target (gap ≤ 10%)
    """
    now = datetime.now(tz=timezone.utc)

    # ------------------------------------------------------------------
    # Macro block
    # ------------------------------------------------------------------
    yc_result = await db.execute(text("""
        SELECT series_id, value, observed_date FROM macro_observations
        WHERE series_id IN ('TREASURY_10Y', 'TREASURY_2Y', 'YIELD_10Y_2Y', 'FED_FUNDS_RATE')
        ORDER BY observed_date DESC
        LIMIT 8
    """))
    yc_rows: dict[str, float] = {}
    obs_date: Optional[str] = None
    for row in yc_result:
        sid, val, obs = row[0], row[1], row[2]
        if sid not in yc_rows and val is not None:
            yc_rows[sid] = float(val)
            if obs_date is None:
                obs_date = str(obs)

    t10 = yc_rows.get("TREASURY_10Y")
    t2  = yc_rows.get("TREASURY_2Y")
    spread = yc_rows.get("YIELD_10Y_2Y") or ((t10 - t2) if (t10 and t2) else None)
    if spread is not None:
        yc_signal = "INVERTED" if spread < 0 else ("FLAT" if spread < 0.5 else "NORMAL")
    else:
        yc_signal = None

    # macro impact score sederhana berdasarkan spread saja
    impact_score: Optional[float] = None
    if spread is not None:
        impact_score = max(-1.0, min(1.0, spread / 3.0))

    macro_block = SummaryMacroBlock(
        yield_curve_signal=yc_signal,
        macro_impact_score=round(impact_score, 3) if impact_score is not None else None,
        fed_funds_rate=yc_rows.get("FED_FUNDS_RATE"),
        as_of=obs_date,
    )

    # ------------------------------------------------------------------
    # Swing setups — sample instrumen aktif
    # ------------------------------------------------------------------
    instr_result = await db.execute(
        select(Instrument)
        .where(Instrument.status == "ACTIVE")
        .order_by(Instrument.id)
        .limit(_SWING_SAMPLE)
    )
    instruments = instr_result.scalars().all()

    swing_items: list[SummarySwingItem] = []
    for instr in instruments:
        if len(swing_items) >= swing_limit:
            break
        df = await _load_df(instr.id, db)
        if df.empty:
            continue
        setup = detect_swing_setup(instr.id, instr.canonical_symbol, df)
        if setup.setup_type in (SetupType.BREAKOUT, SetupType.PULLBACK):
            swing_items.append(SummarySwingItem(
                symbol=instr.canonical_symbol,
                setup_type=setup.setup_type.value,
                strength=setup.strength.value,
                rr_ratio=setup.risk_reward_ratio,
                entry_low=setup.entry_zone_low,
                entry_high=setup.entry_zone_high,
            ))

    # ------------------------------------------------------------------
    # Recent alerts
    # ------------------------------------------------------------------
    alert_result = await db.execute(
        select(Alert)
        .order_by(Alert.created_at.desc())
        .limit(_ALERT_HISTORY)
    )
    alert_items: list[SummaryAlertItem] = []
    for a in alert_result.scalars().all():
        payload = a.payload or {}
        alert_items.append(SummaryAlertItem(
            rule_type=a.event_type,
            symbol=None,
            message=payload.get("message", a.event_type),
            fired_at=a.created_at or now,
        ))

    # ------------------------------------------------------------------
    # Watchlist items near price target
    # ------------------------------------------------------------------
    wi_result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.price_target.isnot(None))
    )
    watch_items: list[SummaryWatchItem] = []
    for wi in wi_result.scalars().all():
        end   = date.today()
        start = end - timedelta(days=5)
        price_res = await db.execute(
            select(PriceBar.close)
            .where(PriceBar.instrument_id == wi.instrument_id,
                   PriceBar.session_date.between(start, end))
            .order_by(PriceBar.session_date.desc())
            .limit(1)
        )
        raw_price = price_res.scalar_one_or_none()
        if raw_price is None or wi.price_target is None:
            continue
        last_price = float(raw_price)
        target = float(wi.price_target)
        pct = ((target / last_price) - 1) * 100

        # Hanya tampilkan yang masih di bawah target, dalam radius _NEAR_TARGET_PCT
        if 0 <= pct <= _NEAR_TARGET_PCT:
            instr_res2 = await db.execute(select(Instrument).where(Instrument.id == wi.instrument_id))
            instr2 = instr_res2.scalar_one_or_none()
            sym = instr2.canonical_symbol if instr2 else wi.instrument_id
            watch_items.append(SummaryWatchItem(
                symbol=sym,
                last_price=last_price,
                price_target=target,
                pct_to_target=round(pct, 2),
            ))

    return DashboardSummaryResponse(
        as_of=now,
        macro=macro_block,
        top_swing_setups=swing_items,
        recent_alerts=alert_items,
        watchlist_near_target=watch_items,
    )
