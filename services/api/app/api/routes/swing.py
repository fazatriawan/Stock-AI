"""
R18 — Swing Trade Monitor routes.

GET /swing/{symbol}       → Deteksi setup swing trade untuk satu instrumen.
GET /swing                → Screen semua instrumen aktif, kembalikan yang punya setup.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

import structlog
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.swing import SetupStrength, SetupType, detect_swing_setup
from app.api.schemas import SwingSetupResponse, SwingScreenResponse
from app.db.models import Instrument, PriceBar
from app.db.session import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/swing", tags=["swing"])

_PRICE_DAYS = 300
_MAX_INSTRUMENTS = 200

_STRENGTH_ORDER = {
    SetupStrength.STRONG:   0,
    SetupStrength.MODERATE: 1,
    SetupStrength.WEAK:     2,
}


async def _load_price_df(instrument_id: str, db: AsyncSession) -> pd.DataFrame:
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
        "open":   float(b.open)  if b.open  else None,
        "high":   float(b.high)  if b.high  else float(b.close),
        "low":    float(b.low)   if b.low   else float(b.close),
        "close":  float(b.close),
        "volume": b.volume or 0,
    } for b in bars])


def _to_response(setup, instr: Instrument) -> SwingSetupResponse:
    return SwingSetupResponse(
        instrument_id=instr.id,
        symbol=instr.canonical_symbol,
        company_name=instr.company_name,
        sector=instr.sector,
        exchange=instr.exchange,
        as_of=setup.as_of,
        setup_type=setup.setup_type.value,
        strength=setup.strength.value,
        current_price=setup.current_price,
        entry_zone_low=setup.entry_zone_low,
        entry_zone_high=setup.entry_zone_high,
        stop_loss_price=setup.stop_loss_price,
        target_price=setup.target_price,
        risk_reward_ratio=setup.risk_reward_ratio,
        atr_14=setup.atr_14,
        resistance_level=setup.resistance_level,
        support_level=setup.support_level,
        rsi_14=setup.rsi_14,
        volume_confirmation=setup.volume_confirmation,
        notes=setup.notes,
        warnings=setup.warnings,
    )


@router.get("/{symbol}", response_model=SwingSetupResponse)
async def get_swing_setup(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> SwingSetupResponse:
    """
    Deteksi setup swing trade untuk satu instrumen.

    Mendeteksi dua jenis setup:
    - **BREAKOUT**: harga menembus resistance 52W, volume konfirmasi, entry saat pullback ke breakout level
    - **PULLBACK**: harga menyentuh SMA50/SMA200/swing low, RSI recovering, entry saat bounce

    Semua harga entry/stop/target bersifat indikatif — bukan sinyal eksekusi.
    """
    result = await db.execute(
        select(Instrument).where(
            (Instrument.canonical_symbol == symbol.upper()) |
            (Instrument.local_symbol == symbol.upper()),
            Instrument.status == "ACTIVE",
        )
    )
    instr = result.scalar_one_or_none()
    if instr is None:
        raise HTTPException(status_code=404, detail=f"Instrumen '{symbol}' tidak ditemukan")

    df = await _load_price_df(instr.id, db)
    if df.empty:
        raise HTTPException(
            status_code=422,
            detail=f"Tidak ada data harga untuk {symbol}. Jalankan /stocks/{symbol}/prices/refresh terlebih dahulu.",
        )

    setup = detect_swing_setup(instr.id, instr.canonical_symbol, df)
    log.info("swing.setup", symbol=symbol, type=setup.setup_type.value, strength=setup.strength.value)
    return _to_response(setup, instr)


@router.get("/screen", response_model=SwingScreenResponse)
async def screen_swing_setups(
    setup_type: Optional[str] = Query(None, description="BREAKOUT atau PULLBACK"),
    min_strength: str = Query("MODERATE", description="Kekuatan minimum: STRONG, MODERATE, WEAK"),
    sector: Optional[str] = Query(None),
    exchange: Optional[str] = Query(None),
    min_rr: Optional[float] = Query(None, description="Risk:Reward minimum (mis. 1.5)"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> SwingScreenResponse:
    """
    Screen semua instrumen aktif dan kembalikan yang memiliki swing setup.

    Diurutkan: strength (STRONG dulu), lalu risk:reward ratio (tinggi dulu).
    """
    # Validasi min_strength
    try:
        strength_cutoff = SetupStrength(min_strength.upper())
    except ValueError:
        strength_cutoff = SetupStrength.MODERATE

    cutoff_order = _STRENGTH_ORDER[strength_cutoff]

    # Validasi setup_type filter
    type_filter: Optional[SetupType] = None
    if setup_type:
        try:
            type_filter = SetupType(setup_type.upper())
        except ValueError:
            pass

    # Ambil instrumen aktif
    query = select(Instrument).where(Instrument.status == "ACTIVE")
    if sector:
        query = query.where(Instrument.sector == sector)
    if exchange:
        query = query.where(Instrument.exchange == exchange)
    query = query.limit(_MAX_INSTRUMENTS)

    result = await db.execute(query)
    instruments = result.scalars().all()

    setups: list[SwingSetupResponse] = []

    for instr in instruments:
        df = await _load_price_df(instr.id, db)
        if df.empty:
            continue

        setup = detect_swing_setup(instr.id, instr.canonical_symbol, df)

        # Skip NO_SETUP
        if setup.setup_type == SetupType.NO_SETUP:
            continue

        # Filter setup_type
        if type_filter and setup.setup_type != type_filter:
            continue

        # Filter strength
        if _STRENGTH_ORDER.get(setup.strength, 99) > cutoff_order:
            continue

        # Filter R:R minimum
        if min_rr is not None and (setup.risk_reward_ratio is None or setup.risk_reward_ratio < min_rr):
            continue

        setups.append(_to_response(setup, instr))

    # Sort: strength dulu, lalu R:R desc
    setups.sort(key=lambda s: (
        _STRENGTH_ORDER.get(SetupStrength(s.strength), 99),
        -(s.risk_reward_ratio or 0),
    ))
    setups = setups[:limit]

    log.info("swing.screen", total=len(setups), min_strength=min_strength)

    return SwingScreenResponse(
        setups=setups,
        total=len(setups),
        setup_type_filter=setup_type,
        min_strength=min_strength,
        as_of=datetime.now(tz=timezone.utc),
    )
