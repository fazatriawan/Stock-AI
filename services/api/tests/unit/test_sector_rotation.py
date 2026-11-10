"""Unit tests untuk Sector Rotation Tracker (pure, tanpa DB)."""
import pandas as pd
from app.analytics.sector_rotation import (
    compute_sector_rotation,
    _momentum_score,
    _signal,
)


def _make_series(returns_pct: list[float], start_price: float = 100.0) -> pd.Series:
    prices = [start_price]
    for r in returns_pct:
        prices.append(prices[-1] * (1 + r / 100))
    idx = pd.date_range("2026-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=idx)


# ---------------------------------------------------------------------------
# _momentum_score
# ---------------------------------------------------------------------------

def test_momentum_score_all_positive():
    score = _momentum_score(2.0, 3.0, 4.0)
    assert score > 0

def test_momentum_score_all_negative():
    score = _momentum_score(-2.0, -3.0, -4.0)
    assert score < 0

def test_momentum_score_missing_1w():
    score = _momentum_score(None, 5.0, 3.0)
    assert score > 0

def test_momentum_score_all_none_returns_zero():
    assert _momentum_score(None, None, None) == 0.0


# ---------------------------------------------------------------------------
# _signal
# ---------------------------------------------------------------------------

def test_signal_accumulate():
    assert _signal(5.0) == "ACCUMULATE"

def test_signal_distribute():
    assert _signal(-5.0) == "DISTRIBUTE"

def test_signal_neutral():
    assert _signal(0.0) == "NEUTRAL"
    assert _signal(2.9) == "NEUTRAL"


# ---------------------------------------------------------------------------
# compute_sector_rotation
# ---------------------------------------------------------------------------

def test_empty_returns_no_rotation():
    result = compute_sector_rotation({})
    assert result.rotation_detected is False
    assert result.all_sectors == []


def test_single_sector_no_rotation():
    prices = {"Finance": _make_series([0.1] * 70)}
    result = compute_sector_rotation({"Finance": prices["Finance"]})
    assert len(result.all_sectors) == 1
    assert result.rotation_detected is False


def test_rotation_detected_large_spread():
    # Finance: strong uptrend, Telco: strong downtrend
    finance = _make_series([1.5] * 70)   # +1.5% per hari
    telco   = _make_series([-1.5] * 70)  # -1.5% per hari
    result = compute_sector_rotation({"Finance": finance, "Telco": telco})
    assert result.rotation_detected is True
    assert "Finance" in result.rotation_note or "Telco" in result.rotation_note


def test_all_sectors_sorted_by_momentum():
    prices = {
        "A": _make_series([0.5] * 70),   # moderate up
        "B": _make_series([1.0] * 70),   # strong up
        "C": _make_series([-0.5] * 70),  # moderate down
    }
    result = compute_sector_rotation(prices)
    scores = [s.momentum_score for s in result.all_sectors]
    assert scores == sorted(scores, reverse=True)


def test_top_sectors_have_accumulate_signal():
    prices = {
        "Finance": _make_series([1.0] * 70),
        "Telco":   _make_series([0.1] * 70),
    }
    result = compute_sector_rotation(prices)
    for s in result.top_sectors:
        assert s.signal == "ACCUMULATE"


def test_as_of_set():
    prices = {"Finance": _make_series([0.5] * 70)}
    result = compute_sector_rotation(prices)
    assert result.as_of is not None
