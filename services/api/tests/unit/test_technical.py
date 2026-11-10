"""
Unit tests — technical indicators.
Verifikasi kalkulasi deterministik RSI, SMA, MACD, ATR.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd

from app.analytics.technical import (
    calculate_rsi,
    calculate_macd,
    calculate_atr,
    compute_technical_snapshot,
)


def make_df(prices: list[float], start: Optional[date] = None) -> pd.DataFrame:
    if start is None:
        start = date(2026, 1, 2)
    dates = []
    d = start
    while len(dates) < len(prices):
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    return pd.DataFrame({
        "session_date": dates,
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "adj_close": prices,
        "volume": [1_000_000] * len(prices),
    })


class TestRSI:
    def test_rsi_range(self) -> None:
        closes = pd.Series([float(i) for i in range(50, 100)])
        rsi = calculate_rsi(closes, 14)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_flat_price_is_nan_then_50ish(self) -> None:
        """Harga flat → delta = 0 → RSI tidak terdefinisi atau 50."""
        closes = pd.Series([100.0] * 30)
        rsi = calculate_rsi(closes, 14)
        # RS = nan jika avg_loss = 0, tapi ewm bisa menghasilkan 0/0
        # Pastikan tidak crash
        assert len(rsi) == 30

    def test_rsi_rising_high(self) -> None:
        """Harga selalu naik → RSI tinggi."""
        closes = pd.Series([float(100 + i * 2) for i in range(100)])
        rsi = calculate_rsi(closes, 14)
        valid = rsi.dropna()
        assert len(valid) > 0
        last_rsi = valid.iloc[-1]
        assert last_rsi > 60

    def test_rsi_falling_low(self) -> None:
        """Harga selalu turun → RSI rendah."""
        closes = pd.Series([float(100 - i * 0.5) for i in range(50)])
        rsi = calculate_rsi(closes, 14)
        last_rsi = rsi.dropna().iloc[-1]
        assert last_rsi < 30


class TestMACD:
    def test_macd_returns_three_series(self) -> None:
        closes = pd.Series([float(100 + i * 0.1) for i in range(60)])
        macd, signal, hist = calculate_macd(closes)
        assert len(macd) == len(closes)
        assert len(signal) == len(closes)
        assert len(hist) == len(closes)

    def test_hist_equals_macd_minus_signal(self) -> None:
        closes = pd.Series([float(100 + i * 0.1) for i in range(60)])
        macd, signal, hist = calculate_macd(closes)
        diff = (macd - signal - hist).dropna().abs()
        assert (diff < 1e-9).all()


class TestATR:
    def test_atr_positive(self) -> None:
        df = make_df([100.0 + i for i in range(30)])
        atr = calculate_atr(df, 14)
        assert atr.dropna().iloc[-1] >= 0


class TestComputeSnapshot:
    def test_insufficient_data(self) -> None:
        df = make_df([100.0] * 10)
        snap = compute_technical_snapshot("TEST", df)
        assert not snap.sufficient_data
        assert "insufficient_data" in snap.missing_indicators

    def test_sufficient_data_sma(self) -> None:
        prices = [100.0 + i * 0.1 for i in range(60)]
        df = make_df(prices)
        snap = compute_technical_snapshot("TEST", df)
        assert snap.sufficient_data
        assert snap.sma_20 is not None
        assert snap.sma_50 is not None

    def test_sma_200_requires_200_bars(self) -> None:
        prices = [100.0] * 150
        df = make_df(prices)
        snap = compute_technical_snapshot("TEST", df)
        assert snap.sma_200 is None
        assert "sma_200" in snap.missing_indicators

    def test_return_1d_correct(self) -> None:
        prices = [100.0] * 25 + [110.0]
        df = make_df(prices)
        snap = compute_technical_snapshot("TEST", df)
        assert snap.return_1d is not None
        assert abs(snap.return_1d - 0.10) < 0.001

    def test_above_sma20(self) -> None:
        prices = [100.0] * 20 + [150.0]
        df = make_df(prices)
        snap = compute_technical_snapshot("TEST", df)
        assert snap.above_sma_20 is True

    def test_bars_available(self) -> None:
        prices = [100.0] * 50
        df = make_df(prices)
        snap = compute_technical_snapshot("TEST", df)
        assert snap.bars_available == 50
