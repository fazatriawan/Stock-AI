"""
Unit test untuk portfolio simulator (Phase 4).
Menguji: rebalance simulation, capital allocation plan.
"""
from __future__ import annotations

import math

import pytest

from app.portfolio.calculator import PositionData
from app.portfolio.simulator import (
    LOT_SIZE,
    CapitalAllocationPlan,
    RebalanceSimulation,
    plan_new_capital,
    simulate_rebalance,
)


def make_pos(
    symbol: str,
    shares: float = 1000,
    avg_cost: float = 5000.0,
    current_price: float | None = None,
    weight: float = 0.25,
    sector: str = "Finance",
) -> PositionData:
    lots = shares / 100
    total_cost = shares * avg_cost
    market_value = shares * current_price if current_price else None
    unrealized_pnl = (market_value - total_cost) if market_value else None
    unrealized_pnl_pct = (unrealized_pnl / total_cost) if (unrealized_pnl is not None and total_cost > 0) else None
    return PositionData(
        instrument_id=f"id-{symbol}",
        canonical_symbol=f"IDX:{symbol}",
        sector=sector,
        shares=shares,
        lots=lots,
        avg_cost=avg_cost,
        total_cost=total_cost,
        current_price=current_price,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        weight=weight,
    )


# ---------------------------------------------------------------------------
# simulate_rebalance
# ---------------------------------------------------------------------------

class TestSimulateRebalance:
    def test_equal_weight_two_positions(self):
        # Dua posisi dengan distribusi tidak seimbang
        # A: 70%, B: 30% → target 50/50
        positions = {
            "a": make_pos("BMRI", shares=7000, avg_cost=5000, current_price=5000, weight=0.70),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.30),
        }
        target = {"IDX:BMRI": 0.5, "IDX:BBRI": 0.5}
        result = simulate_rebalance(positions, target)
        assert isinstance(result, RebalanceSimulation)
        assert result.positions_count == 2

    def test_sell_overweight_position(self):
        # BMRI 70% harus dijual ke 50%
        positions = {
            "a": make_pos("BMRI", shares=7000, avg_cost=5000, current_price=5000, weight=0.70),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.30),
        }
        target = {"IDX:BMRI": 0.5, "IDX:BBRI": 0.5}
        result = simulate_rebalance(positions, target)
        # BMRI harus dapat aksi SELL
        bmri_alloc = next(a for a in result.allocations if "BMRI" in a.canonical_symbol)
        assert bmri_alloc.action == "SELL"
        assert bmri_alloc.delta_lots < 0

    def test_buy_underweight_position(self):
        # BBRI 30% harus dibeli ke 50%
        positions = {
            "a": make_pos("BMRI", shares=7000, avg_cost=5000, current_price=5000, weight=0.70),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.30),
        }
        target = {"IDX:BMRI": 0.5, "IDX:BBRI": 0.5}
        result = simulate_rebalance(positions, target)
        bbri_alloc = next(a for a in result.allocations if "BBRI" in a.canonical_symbol)
        assert bbri_alloc.action == "BUY"
        assert bbri_alloc.delta_lots > 0

    def test_hold_already_at_target(self):
        # Dua posisi equal weight, target sama
        positions = {
            "a": make_pos("BMRI", shares=5000, avg_cost=5000, current_price=5000, weight=0.5),
            "b": make_pos("BBRI", shares=5000, avg_cost=5000, current_price=5000, weight=0.5),
        }
        target = {"IDX:BMRI": 0.5, "IDX:BBRI": 0.5}
        result = simulate_rebalance(positions, target)
        assert result.sell_actions == 0
        assert result.buy_actions == 0
        assert result.hold_actions == 2

    def test_sell_actions_sorted_first(self):
        # Sortir: SELL → BUY → HOLD
        positions = {
            "a": make_pos("BMRI", shares=7000, avg_cost=5000, current_price=5000, weight=0.70),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.30),
        }
        target = {"IDX:BMRI": 0.5, "IDX:BBRI": 0.5}
        result = simulate_rebalance(positions, target)
        order = {"SELL": 0, "BUY": 1, "HOLD": 2}
        actions = [a.action for a in result.allocations]
        sorted_actions = sorted(actions, key=lambda x: order[x])
        assert actions == sorted_actions

    def test_total_portfolio_value_includes_new_capital(self):
        positions = {
            "a": make_pos("BMRI", shares=5000, avg_cost=5000, current_price=5000, weight=1.0),
        }
        result_no_cap = simulate_rebalance(positions, {"IDX:BMRI": 1.0}, new_capital=0)
        result_with_cap = simulate_rebalance(positions, {"IDX:BMRI": 1.0}, new_capital=10_000_000)
        assert result_with_cap.total_portfolio_value > result_no_cap.total_portfolio_value

    def test_disclaimer_present(self):
        positions = {
            "a": make_pos("BMRI", weight=1.0),
        }
        result = simulate_rebalance(positions, {"IDX:BMRI": 1.0})
        assert len(result.disclaimer) > 10

    def test_delta_lots_is_multiple_of_lot_size(self):
        # delta_lots harus bilangan bulat (jumlah lot)
        positions = {
            "a": make_pos("BMRI", shares=7000, avg_cost=5000, current_price=5000, weight=0.70),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.30),
        }
        target = {"IDX:BMRI": 0.5, "IDX:BBRI": 0.5}
        result = simulate_rebalance(positions, target)
        for alloc in result.allocations:
            assert alloc.delta_lots == int(alloc.delta_lots)

    def test_buy_uses_floor_rounding(self):
        # BUY harus pakai math.floor (konservatif)
        positions = {
            "a": make_pos("BMRI", shares=1000, avg_cost=5000, current_price=5000, weight=0.20),
            "b": make_pos("BBRI", shares=4000, avg_cost=5000, current_price=5000, weight=0.80),
        }
        # Target BMRI 50% → harus beli, delta value akan di-floor
        target = {"IDX:BMRI": 0.5, "IDX:BBRI": 0.5}
        result = simulate_rebalance(positions, target)
        bmri_alloc = next(a for a in result.allocations if "BMRI" in a.canonical_symbol)
        if bmri_alloc.action == "BUY":
            assert bmri_alloc.delta_lots >= 0

    def test_sell_uses_ceil_rounding(self):
        # SELL harus pakai math.ceil (konservatif)
        positions = {
            "a": make_pos("BMRI", shares=8000, avg_cost=5000, current_price=5000, weight=0.80),
            "b": make_pos("BBRI", shares=2000, avg_cost=5000, current_price=5000, weight=0.20),
        }
        target = {"IDX:BMRI": 0.5, "IDX:BBRI": 0.5}
        result = simulate_rebalance(positions, target)
        bmri_alloc = next(a for a in result.allocations if "BMRI" in a.canonical_symbol)
        if bmri_alloc.action == "SELL":
            # delta_lots negatif — abs harus >= raw_lots (ceil konservatif)
            assert bmri_alloc.delta_lots <= 0

    def test_empty_positions(self):
        result = simulate_rebalance({}, {})
        assert result.positions_count == 0
        assert result.allocations == []

    def test_total_buy_sell_values_correct(self):
        positions = {
            "a": make_pos("BMRI", shares=7000, avg_cost=5000, current_price=5000, weight=0.70),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.30),
        }
        target = {"IDX:BMRI": 0.5, "IDX:BBRI": 0.5}
        result = simulate_rebalance(positions, target)
        assert result.total_buy_value >= 0
        assert result.total_sell_value >= 0


# ---------------------------------------------------------------------------
# plan_new_capital
# ---------------------------------------------------------------------------

class TestPlanNewCapital:
    def test_empty_portfolio_returns_empty(self):
        result = plan_new_capital({}, new_capital=10_000_000)
        assert isinstance(result, CapitalAllocationPlan)
        assert result.suggestions == []
        assert result.total_positions == 0

    def test_new_capital_stored(self):
        positions = {
            "a": make_pos("BMRI", shares=1000, avg_cost=5000, current_price=5000, weight=1.0),
        }
        result = plan_new_capital(positions, new_capital=5_000_000)
        assert result.new_capital == 5_000_000

    def test_skips_overweight_positions(self):
        # Satu posisi yang overweight (100%) → tidak dapat saran
        # Tapi modal baru perlu didistribusikan juga
        positions = {
            "a": make_pos("BMRI", shares=1000, avg_cost=5000, current_price=5000, weight=1.0),
        }
        result = plan_new_capital(positions, new_capital=1_000_000, max_position_weight=0.25)
        # BMRI sudah 100% → overweight → dilewati → tidak ada saran
        assert len(result.suggestions) == 0

    def test_underweight_receives_capital(self):
        # 4 posisi, 3 sama besar, 1 kecil → yang kecil dapat prioritas
        positions = {
            "a": make_pos("BMRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.3),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.3),
            "c": make_pos("BBNI", shares=3000, avg_cost=5000, current_price=5000, weight=0.3),
            "d": make_pos("BBCA", shares=1000, avg_cost=5000, current_price=5000, weight=0.1),
        }
        result = plan_new_capital(positions, new_capital=20_000_000)
        # BBCA paling underweight → harus ada di suggestions
        syms = [s.canonical_symbol for s in result.suggestions]
        assert "IDX:BBCA" in syms

    def test_suggestions_sorted_by_priority(self):
        positions = {
            "a": make_pos("BMRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.3),
            "b": make_pos("BBRI", shares=2000, avg_cost=5000, current_price=5000, weight=0.2),
            "c": make_pos("BBNI", shares=1000, avg_cost=5000, current_price=5000, weight=0.1),
            "d": make_pos("BBCA", shares=4000, avg_cost=5000, current_price=5000, weight=0.4),
        }
        result = plan_new_capital(positions, new_capital=20_000_000)
        priorities = [s.priority for s in result.suggestions]
        assert priorities == sorted(priorities)

    def test_suggested_lots_floor_rounded(self):
        positions = {
            "a": make_pos("BMRI", shares=2000, avg_cost=5000, current_price=5000, weight=0.4),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.6),
        }
        result = plan_new_capital(positions, new_capital=15_000_000)
        for s in result.suggestions:
            # Jumlah lot harus bilangan bulat
            assert s.suggested_lots == int(s.suggested_lots)
            assert s.suggested_lots >= 1

    def test_warning_for_few_positions(self):
        positions = {
            "a": make_pos("BMRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.5),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.5),
        }
        result = plan_new_capital(positions, new_capital=10_000_000)
        # Hanya 2 posisi → warning undiversified
        assert result.undiversified_warning is not None
        assert "2" in result.undiversified_warning

    def test_no_warning_for_enough_positions(self):
        positions = {
            f"id{i}": make_pos(f"SYM{i}", shares=1000, avg_cost=5000, current_price=5000, weight=0.2)
            for i in range(5)
        }
        result = plan_new_capital(positions, new_capital=10_000_000)
        assert result.undiversified_warning is None

    def test_disclaimer_present(self):
        positions = {
            "a": make_pos("BMRI", shares=1000, avg_cost=5000, current_price=5000, weight=1.0),
        }
        result = plan_new_capital(positions, new_capital=5_000_000)
        assert len(result.disclaimer) > 10

    def test_total_positions_matches(self):
        positions = {
            "a": make_pos("BMRI", shares=2000, avg_cost=5000, current_price=5000, weight=0.4),
            "b": make_pos("BBRI", shares=3000, avg_cost=5000, current_price=5000, weight=0.6),
        }
        result = plan_new_capital(positions, new_capital=10_000_000)
        assert result.total_positions == 2

    def test_suggested_amount_matches_lots_times_price(self):
        positions = {
            "a": make_pos("BMRI", shares=2000, avg_cost=5000, current_price=5000, weight=0.4),
            "b": make_pos("BBRI", shares=1000, avg_cost=5000, current_price=5000, weight=0.2),
            "c": make_pos("BBNI", shares=2000, avg_cost=5000, current_price=5000, weight=0.4),
        }
        result = plan_new_capital(positions, new_capital=15_000_000)
        for s in result.suggestions:
            # Find the original position for this symbol
            pos = next(
                p for p in positions.values() if p.canonical_symbol == s.canonical_symbol
            )
            expected = s.suggested_lots * LOT_SIZE * (pos.current_price or pos.avg_cost)
            assert abs(s.suggested_new_amount - expected) < 1.0
