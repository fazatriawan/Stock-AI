"""
R18 — Swing Trade Monitor.

Mendeteksi dua jenis setup swing trade pada data OHLCV:
1. BREAKOUT  — harga menembus resistance (52W high atau swing high 20 hari)
   Entry: pullback ke breakout level; Stop: 1.5×ATR di bawah entry; Target: 2×R
2. PULLBACK  — harga pullback ke support (SMA50/SMA200 atau swing low 20 hari)
   Entry: bounce dari support; Stop: 1×ATR di bawah support; Target: 1.5×R

Output per instrumen:
- SetupType: BREAKOUT / PULLBACK / NO_SETUP
- Strength: STRONG / MODERATE / WEAK
- entry_zone_low, entry_zone_high
- stop_loss_price
- target_price
- risk_reward_ratio
- Alignment IPS: cek max position size

Batasan V1:
- Hanya long
- Stop-loss berbasis ATR (bukan % fixed)
- Tidak ada real-time tick — hanya EOD
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

import pandas as pd


class SetupType(str, Enum):
    BREAKOUT  = "BREAKOUT"
    PULLBACK  = "PULLBACK"
    NO_SETUP  = "NO_SETUP"


class SetupStrength(str, Enum):
    STRONG   = "STRONG"
    MODERATE = "MODERATE"
    WEAK     = "WEAK"


@dataclass
class SwingSetup:
    instrument_id: str
    symbol: str
    as_of: date
    setup_type: SetupType
    strength: SetupStrength

    current_price: float

    # Entry
    entry_zone_low: Optional[float]
    entry_zone_high: Optional[float]

    # Risk management
    stop_loss_price: Optional[float]
    target_price: Optional[float]
    risk_reward_ratio: Optional[float]   # target_distance / stop_distance

    # Konteks
    atr_14: Optional[float]
    resistance_level: Optional[float]
    support_level: Optional[float]
    rsi_14: Optional[float]
    volume_confirmation: bool    # True jika volume breakout > 1.5× avg

    notes: list[str]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MIN_BARS = 50


def _atr(df: pd.DataFrame, n: int = 14) -> Optional[float]:
    if len(df) < n + 1 or "high" not in df.columns:
        return None
    h = df["high"].astype(float)
    low = df["low"].astype(float)
    c = df["close"].astype(float)
    cp = c.shift(1)
    tr = pd.concat([h - low, (h - cp).abs(), (low - cp).abs()], axis=1).max(axis=1)
    atr_val = tr.ewm(com=n - 1, min_periods=n).mean().iloc[-1]
    return float(atr_val) if not pd.isna(atr_val) else None


def _sma(series: pd.Series, n: int) -> Optional[float]:
    if len(series) < n:
        return None
    return float(series.tail(n).mean())


def _rsi(series: pd.Series, n: int = 14) -> Optional[float]:
    if len(series) < n + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    last_loss = loss.iloc[-1]
    last_gain = gain.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return float(100 - 100 / (1 + rs))


def _swing_high(closes: pd.Series, window: int = 20) -> float:
    return float(closes.tail(window).max())


def _swing_low(closes: pd.Series, window: int = 20) -> float:
    return float(closes.tail(window).min())


def _volume_spike(df: pd.DataFrame, multiplier: float = 1.5) -> bool:
    if "volume" not in df.columns or len(df) < 21:
        return False
    vols = df["volume"].astype(float)
    avg_vol = float(vols.tail(21).iloc[:-1].mean())
    last_vol = float(vols.iloc[-1])
    return avg_vol > 0 and last_vol >= avg_vol * multiplier


# ---------------------------------------------------------------------------
# Breakout detector
# ---------------------------------------------------------------------------

def _detect_breakout(
    df: pd.DataFrame,
    symbol: str,
    instrument_id: str,
    atr: Optional[float],
    rsi: Optional[float],
) -> SwingSetup:
    closes = df["close"].astype(float)
    current = float(closes.iloc[-1])

    # Resistance = max 52W (atau max available jika < 252 bars)
    lookback = min(252, len(closes) - 1)
    resistance = float(closes.iloc[-lookback - 1 : -1].max())   # exclude hari ini

    notes: list[str] = []
    warnings: list[str] = []

    # Apakah hari ini breakout (close > resistance)?
    is_breakout = current > resistance * 0.995   # toleransi 0.5%
    vol_confirm = _volume_spike(df)

    if not is_breakout:
        return SwingSetup(
            instrument_id=instrument_id, symbol=symbol, as_of=df["session_date"].iloc[-1],
            setup_type=SetupType.NO_SETUP, strength=SetupStrength.WEAK,
            current_price=current, entry_zone_low=None, entry_zone_high=None,
            stop_loss_price=None, target_price=None, risk_reward_ratio=None,
            atr_14=atr, resistance_level=resistance, support_level=None,
            rsi_14=rsi, volume_confirmation=False, notes=[], warnings=[],
        )

    # Strength
    if vol_confirm and rsi is not None and rsi > 55:
        strength = SetupStrength.STRONG
        notes.append(f"Breakout kuat: volume spike + RSI={rsi:.1f}")
    elif vol_confirm or (rsi is not None and rsi > 50):
        strength = SetupStrength.MODERATE
        notes.append("Breakout moderat")
    else:
        strength = SetupStrength.WEAK
        notes.append("Breakout lemah: volume rendah, konfirmasi kurang")

    # Entry zone: pullback ke resistance (resistance ± ATR/2)
    atr_safe = atr if atr else current * 0.02
    entry_low  = resistance - atr_safe * 0.5
    entry_high = resistance + atr_safe * 0.5

    # Stop loss: 1.5×ATR di bawah resistance
    stop = resistance - atr_safe * 1.5
    # Target: 2×R dari entry_mid
    entry_mid = (entry_low + entry_high) / 2
    risk      = entry_mid - stop
    target    = entry_mid + risk * 2.0
    rr        = round((target - entry_mid) / risk, 2) if risk > 0 else None

    notes.append(f"Resistance={resistance:.2f}, Entry={entry_low:.2f}–{entry_high:.2f}")
    notes.append(f"Stop={stop:.2f}, Target={target:.2f}, R:R={rr}")

    return SwingSetup(
        instrument_id=instrument_id, symbol=symbol, as_of=df["session_date"].iloc[-1],
        setup_type=SetupType.BREAKOUT, strength=strength,
        current_price=current,
        entry_zone_low=round(entry_low, 2), entry_zone_high=round(entry_high, 2),
        stop_loss_price=round(stop, 2), target_price=round(target, 2),
        risk_reward_ratio=rr,
        atr_14=atr, resistance_level=round(resistance, 2), support_level=None,
        rsi_14=rsi, volume_confirmation=vol_confirm,
        notes=notes, warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Pullback detector
# ---------------------------------------------------------------------------

def _detect_pullback(
    df: pd.DataFrame,
    symbol: str,
    instrument_id: str,
    atr: Optional[float],
    rsi: Optional[float],
) -> SwingSetup:
    closes = df["close"].astype(float)
    current = float(closes.iloc[-1])

    sma50  = _sma(closes, 50)
    sma200 = _sma(closes, 200)

    notes: list[str] = []
    warnings: list[str] = []

    # Pilih support level terkuat yang tersedia
    support: Optional[float] = None
    support_label = ""
    if sma50 and abs(current - sma50) / sma50 < 0.03:
        support = sma50
        support_label = "SMA50"
    elif sma200 and abs(current - sma200) / sma200 < 0.05:
        support = sma200
        support_label = "SMA200"
    else:
        # Fallback: swing low 20 hari
        swing_low = _swing_low(closes.iloc[:-1], 20)
        if abs(current - swing_low) / swing_low < 0.04:
            support = swing_low
            support_label = "SwingLow20"

    if support is None:
        return SwingSetup(
            instrument_id=instrument_id, symbol=symbol, as_of=df["session_date"].iloc[-1],
            setup_type=SetupType.NO_SETUP, strength=SetupStrength.WEAK,
            current_price=current, entry_zone_low=None, entry_zone_high=None,
            stop_loss_price=None, target_price=None, risk_reward_ratio=None,
            atr_14=atr, resistance_level=None, support_level=None,
            rsi_14=rsi, volume_confirmation=False, notes=[], warnings=[],
        )

    # Konfirmasi: harga di atas support & RSI oversold/recovering
    is_above_support = current >= support * 0.99
    rsi_recovering   = rsi is not None and 30 <= rsi <= 50

    if is_above_support and rsi_recovering:
        strength = SetupStrength.STRONG
        notes.append(f"Pullback ke {support_label}={support:.2f}, RSI recovering ({rsi:.1f})")
    elif is_above_support:
        strength = SetupStrength.MODERATE
        notes.append(f"Pullback ke {support_label}={support:.2f}")
    else:
        strength = SetupStrength.WEAK
        warnings.append(f"Harga sedikit di bawah {support_label} — tunggu konfirmasi")

    atr_safe = atr if atr else current * 0.02
    entry_low  = support - atr_safe * 0.3
    entry_high = support + atr_safe * 0.3

    # Stop: 1×ATR di bawah support
    stop = support - atr_safe * 1.0
    entry_mid = (entry_low + entry_high) / 2
    risk      = entry_mid - stop

    # Target: swing high sebelumnya (atau 1.5×R)
    swing_high = _swing_high(closes.iloc[:-1], 20)
    if swing_high > entry_mid:
        target = swing_high
        rr = round((target - entry_mid) / risk, 2) if risk > 0 else None
    else:
        target = entry_mid + risk * 1.5
        rr = 1.5

    notes.append(f"Entry={entry_low:.2f}–{entry_high:.2f}, Stop={stop:.2f}, Target={target:.2f}, R:R={rr}")

    return SwingSetup(
        instrument_id=instrument_id, symbol=symbol, as_of=df["session_date"].iloc[-1],
        setup_type=SetupType.PULLBACK, strength=strength,
        current_price=current,
        entry_zone_low=round(entry_low, 2), entry_zone_high=round(entry_high, 2),
        stop_loss_price=round(stop, 2), target_price=round(target, 2),
        risk_reward_ratio=rr,
        atr_14=atr, resistance_level=None, support_level=round(support, 2),
        rsi_14=rsi, volume_confirmation=False,
        notes=notes, warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_swing_setup(
    instrument_id: str,
    symbol: str,
    df: pd.DataFrame,
) -> SwingSetup:
    """
    Deteksi swing setup dari DataFrame OHLCV.
    df harus punya kolom: session_date, close (dan idealnya high, low, volume).
    Diurutkan ascending.
    """
    if df.empty or len(df) < _MIN_BARS:
        return SwingSetup(
            instrument_id=instrument_id, symbol=symbol,
            as_of=date.today(),
            setup_type=SetupType.NO_SETUP, strength=SetupStrength.WEAK,
            current_price=0.0, entry_zone_low=None, entry_zone_high=None,
            stop_loss_price=None, target_price=None, risk_reward_ratio=None,
            atr_14=None, resistance_level=None, support_level=None,
            rsi_14=None, volume_confirmation=False,
            notes=[], warnings=[f"Data tidak cukup: {len(df)} bar, minimal {_MIN_BARS}"],
        )

    df = df.sort_values("session_date").reset_index(drop=True)
    closes = df["close"].astype(float)
    atr    = _atr(df)
    rsi    = _rsi(closes)

    # Coba breakout dulu
    breakout = _detect_breakout(df, symbol, instrument_id, atr, rsi)
    if breakout.setup_type == SetupType.BREAKOUT:
        return breakout

    # Fallback ke pullback
    return _detect_pullback(df, symbol, instrument_id, atr, rsi)
