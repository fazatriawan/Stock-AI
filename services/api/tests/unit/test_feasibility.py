"""Unit tests untuk Trade Feasibility Engine (R10)."""
from app.decisions.feasibility import (
    FeasibilityStatus,
    check_trade_feasibility,
    _get_tick_size,
    _estimate_spread_pct,
)


# ---------------------------------------------------------------------------
# Tick size tests
# ---------------------------------------------------------------------------

def test_tick_size_very_low():
    assert _get_tick_size(150) == 1.0

def test_tick_size_low():
    assert _get_tick_size(300) == 2.0

def test_tick_size_mid():
    assert _get_tick_size(1000) == 5.0

def test_tick_size_high():
    assert _get_tick_size(3000) == 10.0

def test_tick_size_very_high():
    assert _get_tick_size(10000) == 25.0


# ---------------------------------------------------------------------------
# Spread estimate
# ---------------------------------------------------------------------------

def test_spread_pct_idx_low_price():
    # Rp100 → tick=1 → spread = 1/100 = 1%
    pct = _estimate_spread_pct(100, "IDX")
    assert abs(pct - 0.01) < 1e-6

def test_spread_pct_us():
    pct = _estimate_spread_pct(100, "US")
    assert abs(pct - 0.0005) < 1e-6


# ---------------------------------------------------------------------------
# Feasibility core logic
# ---------------------------------------------------------------------------

def _base_params(**overrides):
    params = dict(
        exchange="IDX",
        last_price=5000.0,       # Rp5.000 → 1 lot = Rp500.000
        available_cash=2_000_000.0,
        portfolio_total_value=50_000_000.0,
        portfolio_weight_current=0.0,
        max_position_weight=0.10,
        adv_shares=None,
        desired_lots=None,
    )
    params.update(overrides)
    return params


def test_feasible_case():
    result = check_trade_feasibility(**_base_params())
    assert result.status == FeasibilityStatus.FEASIBLE
    assert result.lot_size == 100
    assert result.min_cost_estimate == 500_000.0  # Rp5.000 × 100
    assert result.suggested_lots is not None
    assert result.suggested_lots >= 1
    assert result.blockers == []


def test_not_enough_capital():
    # Harga Rp50.000 → 1 lot = Rp5.000.000; dana hanya Rp1.000.000
    result = check_trade_feasibility(**_base_params(
        last_price=50_000.0,
        available_cash=1_000_000.0,
    ))
    assert result.status == FeasibilityStatus.NOT_FEASIBLE
    assert len(result.blockers) > 0
    assert result.suggested_lots is None


def test_ips_position_limit_exceeded():
    # Portfolio Rp100M, bobot sekarang sudah 10% = di batas
    result = check_trade_feasibility(**_base_params(
        portfolio_total_value=100_000_000.0,
        portfolio_weight_current=0.10,  # sudah di batas
        max_position_weight=0.10,
        available_cash=20_000_000.0,
    ))
    assert result.status == FeasibilityStatus.NOT_FEASIBLE
    assert any("IPS" in b for b in result.blockers)


def test_adv_warning_when_order_large():
    # Order 10 lot = 1000 saham; ADV = 5000 saham → 20% ADV
    result = check_trade_feasibility(**_base_params(
        adv_shares=5_000.0,
        desired_lots=10,
    ))
    assert result.status == FeasibilityStatus.MARGINAL
    assert any("ADV" in w for w in result.warnings)
    assert result.adv_ratio is not None
    assert result.adv_ratio > 0.05


def test_adv_ok_small_order():
    # 1 lot = 100 saham; ADV = 100_000 → 0.1%
    result = check_trade_feasibility(**_base_params(
        adv_shares=100_000.0,
        desired_lots=1,
    ))
    assert result.adv_ratio < 0.05


def test_us_exchange_lot_size_1():
    result = check_trade_feasibility(**_base_params(
        exchange="US",
        last_price=150.0,  # USD
        available_cash=10_000.0,
        portfolio_total_value=100_000.0,
    ))
    assert result.lot_size == 1
    assert result.min_cost_estimate == 150.0  # 1 × US$150


def test_invalid_price():
    result = check_trade_feasibility(**_base_params(last_price=0))
    assert result.status == FeasibilityStatus.NOT_FEASIBLE


def test_suggested_lots_respects_desired():
    # Minta 2 lots, kapital dan IPS cukup untuk 10 lots
    result = check_trade_feasibility(**_base_params(
        available_cash=10_000_000.0,
        desired_lots=2,
    ))
    assert result.status == FeasibilityStatus.FEASIBLE
    assert result.suggested_lots == 2


def test_spread_warning_low_price():
    # Rp100/saham → spread ≈ 1% (> 0.5%) → MARGINAL
    result = check_trade_feasibility(**_base_params(
        last_price=100.0,
        available_cash=50_000.0,
    ))
    # Spread check gagal (peringatan) → MARGINAL atau lebih
    assert result.spread_cost_pct is not None
    assert result.spread_cost_pct > 0.005


def test_adv_extreme_illiquidity_hard_block():
    # Order 10 lot = 1000 saham; ADV hanya 2000 saham → 50% ADV (>25%) → NOT_FEASIBLE
    result = check_trade_feasibility(**_base_params(
        adv_shares=2_000.0,
        desired_lots=10,
    ))
    assert result.status == FeasibilityStatus.NOT_FEASIBLE
    assert any("NOT_EXECUTABLE_AT_ASSUMED_SIZE" in b for b in result.blockers)
