"""Unit tests untuk Correlation Engine (pure, tanpa DB)."""
import pandas as pd
import pytest
from app.analytics.correlation import compute_correlation_matrix, _interpret


def _make_series(values: list[float], start: str = "2026-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=idx)


# ---------------------------------------------------------------------------
# _interpret
# ---------------------------------------------------------------------------

def test_interpret_strong_positive():
    assert _interpret(0.85) == "STRONG_POSITIVE"

def test_interpret_moderate_positive():
    assert _interpret(0.55) == "MODERATE_POSITIVE"

def test_interpret_uncorrelated():
    assert _interpret(0.0) == "UNCORRELATED"

def test_interpret_moderate_negative():
    assert _interpret(-0.55) == "MODERATE_NEGATIVE"

def test_interpret_strong_negative():
    assert _interpret(-0.9) == "STRONG_NEGATIVE"


# ---------------------------------------------------------------------------
# compute_correlation_matrix
# ---------------------------------------------------------------------------

def _linear(n: int, up: bool = True) -> list[float]:
    return [100.0 + i * (1 if up else -1) for i in range(n)]


def test_perfect_positive_correlation():
    prices = {
        "BBCA": _make_series(_linear(50)),
        "BBRI": _make_series(_linear(50)),
    }
    result = compute_correlation_matrix(prices)
    assert result.matrix["BBCA"]["BBRI"] == pytest.approx(1.0, abs=0.01)


def test_perfect_negative_correlation():
    # BBCA naik-turun-naik, EXCL turun-naik-turun (return berlawanan persis)
    idx = pd.date_range("2026-01-01", periods=50, freq="B")
    prices_a = [100.0]
    prices_b = [100.0]
    for i in range(49):
        delta = 1.0 if i % 2 == 0 else -1.0
        prices_a.append(prices_a[-1] + delta)
        prices_b.append(prices_b[-1] - delta)
    bbca = pd.Series(prices_a, index=idx)
    excl = pd.Series(prices_b, index=idx)
    result = compute_correlation_matrix({"BBCA": bbca, "EXCL": excl})
    corr = result.matrix["BBCA"]["EXCL"]
    assert corr < -0.9


def test_self_correlation_is_one():
    prices = {"TLKM": _make_series(_linear(50))}
    # hanya 1 instrumen — tidak bisa hitung matrix
    result = compute_correlation_matrix(prices)
    assert "Butuh minimal 2 instrumen" in result.warnings[0]


def test_insufficient_bars_warns():
    prices = {
        "A": _make_series([100.0] * 10),  # < min_bars=30
        "B": _make_series(_linear(50)),
    }
    result = compute_correlation_matrix({"A": prices["A"], "B": prices["B"]}, min_bars=30)
    assert any("dilewati" in w for w in result.warnings)


def test_pairs_sorted_by_abs_correlation():
    import numpy as np
    rng = np.random.default_rng(42)
    n = 60
    base = rng.standard_normal(n)
    prices = {
        "A": _make_series((100 + base.cumsum()).tolist()),
        "B": _make_series((100 + (base + rng.standard_normal(n) * 0.1).cumsum()).tolist()),
        "C": _make_series((100 + rng.standard_normal(n).cumsum()).tolist()),
    }
    result = compute_correlation_matrix(prices)
    corrs = [abs(p.correlation) for p in result.pairs]
    assert corrs == sorted(corrs, reverse=True)


def test_bars_used_reported():
    prices = {
        "A": _make_series(_linear(50)),
        "B": _make_series(_linear(50)),
    }
    result = compute_correlation_matrix(prices)
    assert result.bars_used > 0
