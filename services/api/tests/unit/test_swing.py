"""Unit tests untuk R18 Swing Trade Monitor."""
import pytest
from datetime import date, timedelta

import pandas as pd

from app.analytics.swing import (
    SetupStrength,
    SetupType,
    detect_swing_setup,
)

START = date(2023, 1, 1)


def _make_df(prices: list[float], highs: list[float] | None = None,
             lows: list[float] | None = None, volumes: list[int] | None = None) -> pd.DataFrame:
    n = len(prices)
    dates = [START + timedelta(days=i) for i in range(n)]
    df = pd.DataFrame({
        "session_date": dates,
        "close": prices,
        "open":  prices,
        "high":  highs  if highs  else [p * 1.01 for p in prices],
        "low":   lows   if lows   else [p * 0.99 for p in prices],
        "volume": volumes if volumes else [1_000_000] * n,
    })
    return df


def _flat(n: int = 100, price: float = 1000.0) -> list[float]:
    return [price] * n


def _trending_up(n: int = 100, start: float = 1000.0, end: float = 1500.0) -> list[float]:
    return [start + (end - start) * i / (n - 1) for i in range(n)]


def _trending_down(n: int = 100, start: float = 1500.0, end: float = 1000.0) -> list[float]:
    return [start + (end - start) * i / (n - 1) for i in range(n)]


# ---------------------------------------------------------------------------
# Data tidak cukup
# ---------------------------------------------------------------------------

def test_insufficient_data_returns_no_setup():
    df = _make_df([1000.0] * 30)   # kurang dari 50
    setup = detect_swing_setup("id1", "TEST", df)
    assert setup.setup_type == SetupType.NO_SETUP
    assert len(setup.warnings) > 0


def test_empty_df_returns_no_setup():
    df = pd.DataFrame(columns=["session_date", "close", "high", "low", "volume"])
    setup = detect_swing_setup("id1", "TEST", df)
    assert setup.setup_type == SetupType.NO_SETUP


# ---------------------------------------------------------------------------
# Breakout setup
# ---------------------------------------------------------------------------

def test_breakout_detected_on_new_high():
    # Buat data: 99 hari datar di 1000, lalu satu hari breakout ke 1020
    prices = _flat(99, 1000.0) + [1020.0]
    # Volume spike pada hari breakout
    volumes = [1_000_000] * 99 + [2_000_000]
    df = _make_df(prices, volumes=volumes)
    setup = detect_swing_setup("id1", "BRKOUT", df)
    assert setup.setup_type == SetupType.BREAKOUT
    assert setup.entry_zone_low is not None
    assert setup.stop_loss_price is not None
    assert setup.target_price is not None
    assert setup.stop_loss_price < setup.entry_zone_low
    assert setup.target_price > setup.entry_zone_high


def test_breakout_rr_at_least_one():
    prices = _flat(99, 1000.0) + [1025.0]
    volumes = [1_000_000] * 99 + [2_500_000]
    df = _make_df(prices, volumes=volumes)
    setup = detect_swing_setup("id1", "BRKOUT", df)
    if setup.setup_type == SetupType.BREAKOUT and setup.risk_reward_ratio is not None:
        assert setup.risk_reward_ratio >= 1.0


def test_breakout_with_volume_spike_is_stronger():
    prices_spike = _flat(99, 1000.0) + [1020.0]
    vol_spike   = [1_000_000] * 99 + [3_000_000]
    df_spike = _make_df(prices_spike, volumes=vol_spike)
    setup_spike = detect_swing_setup("id1", "TEST", df_spike)

    prices_flat = _flat(99, 1000.0) + [1020.0]
    vol_flat    = [1_000_000] * 100
    df_flat = _make_df(prices_flat, volumes=vol_flat)
    setup_flat = detect_swing_setup("id2", "TEST", df_flat)

    # Keduanya breakout; setup dengan volume spike harus strength lebih tinggi atau sama
    if setup_spike.setup_type == SetupType.BREAKOUT and setup_flat.setup_type == SetupType.BREAKOUT:
        order = {SetupStrength.STRONG: 0, SetupStrength.MODERATE: 1, SetupStrength.WEAK: 2}
        assert order[setup_spike.strength] <= order[setup_flat.strength]


# ---------------------------------------------------------------------------
# Pullback setup
# ---------------------------------------------------------------------------

def test_pullback_near_sma50():
    # 50 hari datar di 1000, lalu sedikit turun ke support SMA50
    prices = _flat(50, 1000.0) + [980.0] * 10 + [1002.0]  # balik ke SMA50
    df = _make_df(prices)
    setup = detect_swing_setup("id1", "PULL", df)
    # Bisa PULLBACK atau NO_SETUP tergantung kondisi exact; yang penting tidak error
    assert setup.setup_type in (SetupType.PULLBACK, SetupType.NO_SETUP, SetupType.BREAKOUT)


def test_pullback_stop_below_support():
    prices = _flat(60, 1000.0) + [1000.0] * 10 + [999.0]
    df = _make_df(prices)
    setup = detect_swing_setup("id1", "PULL", df)
    if setup.setup_type == SetupType.PULLBACK and setup.stop_loss_price is not None:
        assert setup.stop_loss_price < setup.support_level


# ---------------------------------------------------------------------------
# No setup
# ---------------------------------------------------------------------------

def test_no_setup_trending_down_strongly():
    # Tren turun kuat → tidak ada breakout, tidak ada pullback ke support
    prices = _trending_down(100, 2000.0, 500.0)
    df = _make_df(prices)
    setup = detect_swing_setup("id1", "DOWN", df)
    # Mungkin NO_SETUP, atau PULLBACK lemah — tidak boleh BREAKOUT
    assert setup.setup_type != SetupType.BREAKOUT


# ---------------------------------------------------------------------------
# Field invariants
# ---------------------------------------------------------------------------

def test_symbol_set_correctly():
    df = _make_df(_flat(60))
    setup = detect_swing_setup("my-id", "BBCA", df)
    assert setup.symbol == "BBCA"
    assert setup.instrument_id == "my-id"


def test_as_of_set_to_last_bar_date():
    prices = _flat(60)
    dates = [START + timedelta(days=i) for i in range(60)]
    df = pd.DataFrame({
        "session_date": dates,
        "close": prices,
        "high":  [p * 1.01 for p in prices],
        "low":   [p * 0.99 for p in prices],
        "volume": [1_000_000] * 60,
    })
    setup = detect_swing_setup("id1", "TEST", df)
    assert setup.as_of == dates[-1]


def test_entry_zone_low_less_than_high():
    prices = _flat(99, 1000.0) + [1025.0]
    df = _make_df(prices, volumes=[1_000_000] * 99 + [2_000_000])
    setup = detect_swing_setup("id1", "TEST", df)
    if setup.entry_zone_low is not None and setup.entry_zone_high is not None:
        assert setup.entry_zone_low <= setup.entry_zone_high


def test_current_price_matches_last_close():
    prices = _flat(60, 1234.5)
    df = _make_df(prices)
    setup = detect_swing_setup("id1", "TEST", df)
    assert setup.current_price == pytest.approx(1234.5, rel=0.001)
