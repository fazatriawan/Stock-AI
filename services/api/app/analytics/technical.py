"""
Deterministic technical indicators.
Semua kalkulasi murni Python/pandas — tidak ada LLM di sini.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class TechnicalSnapshot:
    as_of: date
    instrument_id: str
    # Moving averages
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    # Momentum
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    # Volatility
    atr_14: Optional[float] = None
    realized_vol_20: Optional[float] = None
    realized_vol_60: Optional[float] = None
    # Trend signals
    above_sma_20: Optional[bool] = None
    above_sma_50: Optional[bool] = None
    above_sma_200: Optional[bool] = None
    golden_cross: Optional[bool] = None   # SMA50 > SMA200
    death_cross: Optional[bool] = None    # SMA50 < SMA200
    # Volume
    volume_ratio_20: Optional[float] = None  # volume hari ini / avg 20 hari
    avg_volume_20: Optional[float] = None
    # Price levels
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    pct_from_52w_high: Optional[float] = None
    pct_from_52w_low: Optional[float] = None
    percentile_52w: Optional[float] = None
    # Returns
    return_1d: Optional[float] = None
    return_5d: Optional[float] = None
    return_20d: Optional[float] = None
    return_60d: Optional[float] = None
    # Data quality
    bars_available: int = 0
    sufficient_data: bool = False
    missing_indicators: list[str] = field(default_factory=list)


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    # Jika avg_loss = 0, RSI = 100 (tidak ada loss); jika avg_gain = 0, RSI = 0
    result = pd.Series(index=closes.index, dtype=float)
    no_loss = avg_loss == 0
    no_gain = avg_gain == 0
    both_zero = no_loss & no_gain
    result[both_zero] = np.nan
    result[~both_zero & no_loss] = 100.0
    result[~both_zero & no_gain] = 0.0
    normal = ~both_zero & ~no_loss & ~no_gain
    rs = avg_gain[normal] / avg_loss[normal]
    result[normal] = 100 - (100 / (1 + rs))
    return result


def calculate_macd(
    closes: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = closes.ewm(span=fast, min_periods=fast).mean()
    ema_slow = closes.ewm(span=slow, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_atr(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    """True Range dan ATR. df harus punya kolom High, Low, Close."""
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low - close_prev).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def compute_technical_snapshot(
    instrument_id: str,
    df: pd.DataFrame,
    as_of: date | None = None,
) -> TechnicalSnapshot:
    """
    Hitung semua technical indicators dari DataFrame OHLCV.
    df harus memiliki kolom: session_date, open, high, low, close, adj_close, volume.
    df harus diurutkan ascending berdasarkan session_date.
    """
    snap = TechnicalSnapshot(
        as_of=as_of or (df["session_date"].max() if len(df) > 0 else date.today()),
        instrument_id=instrument_id,
        bars_available=len(df),
    )

    if len(df) < 20:
        snap.missing_indicators = ["insufficient_data"]
        return snap

    snap.sufficient_data = True
    df = df.sort_values("session_date").copy()
    closes = df["close"].astype(float)
    volumes = df["volume"].astype(float)

    # Moving averages
    if len(df) >= 20:
        snap.sma_20 = float(closes.tail(20).mean())
        snap.ema_20 = float(closes.ewm(span=20, min_periods=20).mean().iloc[-1])
        snap.above_sma_20 = float(closes.iloc[-1]) > snap.sma_20
    else:
        snap.missing_indicators.append("sma_20")

    if len(df) >= 50:
        snap.sma_50 = float(closes.tail(50).mean())
        snap.ema_50 = float(closes.ewm(span=50, min_periods=50).mean().iloc[-1])
        snap.above_sma_50 = float(closes.iloc[-1]) > snap.sma_50
    else:
        snap.missing_indicators.append("sma_50")

    if len(df) >= 200:
        snap.sma_200 = float(closes.tail(200).mean())
        snap.above_sma_200 = float(closes.iloc[-1]) > snap.sma_200
        if snap.sma_50 is not None:
            snap.golden_cross = snap.sma_50 > snap.sma_200
            snap.death_cross = snap.sma_50 < snap.sma_200
    else:
        snap.missing_indicators.append("sma_200")

    # RSI
    if len(df) >= 28:
        rsi_series = calculate_rsi(closes, 14)
        snap.rsi_14 = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None
    else:
        snap.missing_indicators.append("rsi_14")

    # MACD
    if len(df) >= 35:
        macd_line, signal_line, histogram = calculate_macd(closes)
        snap.macd = float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else None
        snap.macd_signal = float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else None
        snap.macd_hist = float(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else None
    else:
        snap.missing_indicators.append("macd")

    # ATR
    if len(df) >= 28 and "high" in df.columns and "low" in df.columns:
        atr_series = calculate_atr(df, 14)
        snap.atr_14 = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else None
    else:
        snap.missing_indicators.append("atr_14")

    # Realized volatility
    log_returns = np.log(closes / closes.shift(1)).dropna()
    if len(log_returns) >= 20:
        snap.realized_vol_20 = float(log_returns.tail(20).std() * np.sqrt(252))
    if len(log_returns) >= 60:
        snap.realized_vol_60 = float(log_returns.tail(60).std() * np.sqrt(252))

    # 52-week stats
    days_252 = df.tail(252)
    if len(days_252) >= 20:
        snap.high_52w = float(days_252["high"].max())
        snap.low_52w = float(days_252["low"].min())
        last_close = float(closes.iloc[-1])
        if snap.high_52w > 0:
            snap.pct_from_52w_high = (last_close - snap.high_52w) / snap.high_52w
        if snap.low_52w > 0:
            snap.pct_from_52w_low = (last_close - snap.low_52w) / snap.low_52w
        close_range = snap.high_52w - snap.low_52w
        if close_range > 0:
            snap.percentile_52w = (last_close - snap.low_52w) / close_range

    # Returns
    last = float(closes.iloc[-1])
    if len(closes) >= 2:
        snap.return_1d = (last / float(closes.iloc[-2]) - 1)
    if len(closes) >= 6:
        snap.return_5d = (last / float(closes.iloc[-6]) - 1)
    if len(closes) >= 21:
        snap.return_20d = (last / float(closes.iloc[-21]) - 1)
    if len(closes) >= 61:
        snap.return_60d = (last / float(closes.iloc[-61]) - 1)

    # Volume ratio
    if len(volumes) >= 20 and volumes.tail(20).mean() > 0:
        snap.avg_volume_20 = float(volumes.tail(20).mean())
        snap.volume_ratio_20 = float(volumes.iloc[-1]) / snap.avg_volume_20

    return snap
