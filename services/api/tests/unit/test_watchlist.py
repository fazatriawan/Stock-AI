"""Unit tests untuk R20 Watchlist price-target helper logic (pure, tanpa DB)."""
import pytest


# ---------------------------------------------------------------------------
# Helper: replicate _enrich_item logic (tanpa import route agar pure)
# ---------------------------------------------------------------------------

def _pct_to_target(price_target: float | None, last_price: float | None) -> float | None:
    if price_target and last_price:
        return round(((price_target / last_price) - 1) * 100, 2)
    return None


def _pct_from_cost(cost_basis: float | None, last_price: float | None) -> float | None:
    if cost_basis and last_price:
        return round(((last_price / cost_basis) - 1) * 100, 2)
    return None


# ---------------------------------------------------------------------------
# pct_to_target
# ---------------------------------------------------------------------------

def test_pct_to_target_upside():
    # target 10% di atas harga
    result = _pct_to_target(11_000.0, 10_000.0)
    assert result == pytest.approx(10.0)


def test_pct_to_target_downside():
    # target di bawah harga saat ini → negatif
    result = _pct_to_target(9_000.0, 10_000.0)
    assert result == pytest.approx(-10.0)


def test_pct_to_target_no_target():
    assert _pct_to_target(None, 10_000.0) is None


def test_pct_to_target_no_price():
    assert _pct_to_target(10_000.0, None) is None


def test_pct_to_target_at_target():
    assert _pct_to_target(10_000.0, 10_000.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# pct_from_cost
# ---------------------------------------------------------------------------

def test_pct_from_cost_gain():
    result = _pct_from_cost(8_000.0, 10_000.0)
    assert result == pytest.approx(25.0)


def test_pct_from_cost_loss():
    result = _pct_from_cost(12_000.0, 10_000.0)
    assert result == pytest.approx(-16.67)


def test_pct_from_cost_no_cost():
    assert _pct_from_cost(None, 10_000.0) is None


def test_pct_from_cost_no_price():
    assert _pct_from_cost(8_000.0, None) is None


def test_pct_from_cost_breakeven():
    assert _pct_from_cost(10_000.0, 10_000.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_pct_to_target_large_upside():
    # 10x bagger target
    result = _pct_to_target(100_000.0, 10_000.0)
    assert result == pytest.approx(900.0)


def test_pct_from_cost_zero_cost_returns_none():
    # cost_basis = 0 → falsy → None (hindari ZeroDivisionError)
    assert _pct_from_cost(0.0, 10_000.0) is None
