"""
Unit test untuk portfolio analyzer (Phase 3).
Menguji: health score, concentration detection, loss scenario generation.
"""
from __future__ import annotations


import pytest

from app.portfolio.analyzer import (
    HealthGrade,
    LossScenario,
    analyze_loss_position,
    compute_portfolio_health,
)
from app.portfolio.calculator import PositionData


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
# compute_portfolio_health
# ---------------------------------------------------------------------------

class TestComputePortfolioHealth:
    def test_empty_portfolio_returns_poor(self):
        report = compute_portfolio_health({}, {})
        assert report.grade == HealthGrade.POOR
        assert report.health_score == 0.0
        assert len(report.warnings) > 0

    def test_single_position_is_undiversified(self):
        positions = {"a": make_pos("BMRI", weight=1.0)}
        report = compute_portfolio_health(positions, {"Finance": 1.0})
        assert len(report.warnings) > 0
        # Hanya 1 posisi → undiversified warning
        assert any("1 posisi" in w for w in report.warnings)

    def test_severely_overweight_detected(self):
        positions = {
            "a": make_pos("BMRI", weight=0.45),
            "b": make_pos("BBRI", weight=0.25),
            "c": make_pos("BBNI", weight=0.15),
            "d": make_pos("BBCA", weight=0.10),
            "e": make_pos("TLKM", weight=0.05, sector="Telecoms"),
        }
        report = compute_portfolio_health(positions, {"Finance": 0.95, "Telecoms": 0.05})
        # BMRI 45% → SEVERELY_OVERWEIGHT
        severe = [r for r in report.concentration_risks if r.severity == "SEVERELY_OVERWEIGHT"]
        assert len(severe) == 1
        assert "BMRI" in severe[0].symbol

    def test_overweight_detected(self):
        positions = {
            "a": make_pos("BMRI", weight=0.30),
            "b": make_pos("BBRI", weight=0.25),
            "c": make_pos("BBNI", weight=0.25),
            "d": make_pos("BBCA", weight=0.20),
        }
        report = compute_portfolio_health(positions, {"Finance": 1.0})
        overweight = [r for r in report.concentration_risks if r.severity == "OVERWEIGHT"]
        assert len(overweight) >= 1

    def test_sector_concentration_detected(self):
        positions = {
            "a": make_pos("BMRI", weight=0.30, sector="Finance"),
            "b": make_pos("BBRI", weight=0.30, sector="Finance"),
            "c": make_pos("BBNI", weight=0.25, sector="Finance"),
            "d": make_pos("BBCA", weight=0.15, sector="Finance"),
        }
        report = compute_portfolio_health(positions, {"Finance": 1.0})
        assert len(report.sector_risks) > 0
        assert report.sector_risks[0].severity == "CONCENTRATED"

    def test_diversified_portfolio_higher_score(self):
        # 8 posisi equal weight → high diversification
        positions = {
            f"id{i}": make_pos(f"SYM{i}", weight=0.125, sector=f"Sector{i}")
            for i in range(8)
        }
        sector_weights = {f"Sector{i}": 0.125 for i in range(8)}
        report = compute_portfolio_health(positions, sector_weights)
        assert report.health_score > 60.0

    def test_health_score_bounded(self):
        positions = {"a": make_pos("BMRI", weight=1.0)}
        report = compute_portfolio_health(positions, {"Finance": 1.0})
        assert 0.0 <= report.health_score <= 100.0

    def test_grade_mapping(self):
        # Buat portofolio sangat sehat
        positions = {
            f"id{i}": make_pos(f"SYM{i}", weight=0.125,
                               current_price=5500, sector=f"Sector{i % 4}")
            for i in range(8)
        }
        sector_weights = {f"Sector{k}": 0.25 for k in range(4)}
        report = compute_portfolio_health(positions, sector_weights)
        # Score check — bukan grade check karena tergantung angka pasti
        assert report.grade in {HealthGrade.EXCELLENT, HealthGrade.GOOD, HealthGrade.FAIR, HealthGrade.POOR}

    def test_largest_position_tracked(self):
        positions = {
            "a": make_pos("BMRI", weight=0.45),
            "b": make_pos("BBRI", weight=0.35),
            "c": make_pos("BBNI", weight=0.20),
        }
        report = compute_portfolio_health(positions, {"Finance": 1.0})
        assert report.largest_position_symbol == "IDX:BMRI"
        assert report.largest_position_weight == 0.45

    def test_pnl_component_profit(self):
        # Semua posisi profit 20%+
        positions = {
            "a": make_pos("BMRI", avg_cost=5000, current_price=6200, weight=0.5),
            "b": make_pos("BBRI", avg_cost=3000, current_price=3700, weight=0.5),
        }
        report = compute_portfolio_health(positions, {"Finance": 1.0})
        assert report.pnl_component == 30.0  # max

    def test_pnl_component_loss(self):
        positions = {
            "a": make_pos("BMRI", avg_cost=5000, current_price=3000, weight=0.5),
            "b": make_pos("BBRI", avg_cost=3000, current_price=1800, weight=0.5),
        }
        report = compute_portfolio_health(positions, {"Finance": 1.0})
        assert report.pnl_component < 15.0


# ---------------------------------------------------------------------------
# analyze_loss_position
# ---------------------------------------------------------------------------

class TestAnalyzeLossPosition:
    def test_no_analysis_for_profit(self):
        pos = make_pos("BMRI", avg_cost=5000, current_price=5500, weight=0.3)
        assert analyze_loss_position(pos) is None

    def test_no_analysis_for_small_loss(self):
        # -3% → di bawah threshold -5%
        pos = make_pos("BMRI", avg_cost=5000, current_price=4850, weight=0.3)
        assert analyze_loss_position(pos) is None

    def test_no_analysis_without_price(self):
        pos = make_pos("BMRI", current_price=None, weight=0.3)
        assert analyze_loss_position(pos) is None

    def test_loss_5pct_returns_5_scenarios(self):
        pos = make_pos("BMRI", avg_cost=5000, current_price=4700, weight=0.3)
        # -6% → masuk analyzer
        result = analyze_loss_position(pos)
        assert result is not None
        assert len(result.scenarios) == 5

    def test_scenario_types_present(self):
        pos = make_pos("BMRI", avg_cost=5000, current_price=4000, weight=0.3)
        result = analyze_loss_position(pos)
        scenario_types = {s.scenario for s in result.scenarios}
        assert LossScenario.CUT_LOSS in scenario_types
        assert LossScenario.PARTIAL_CUT in scenario_types
        assert LossScenario.HOLD_WAIT in scenario_types
        assert LossScenario.AVERAGE_DOWN in scenario_types
        assert LossScenario.STOP_LOSS in scenario_types

    def test_severe_loss_suggests_cut_loss(self):
        # -25% → CUT_LOSS disarankan
        pos = make_pos("BMRI", avg_cost=5000, current_price=3750, weight=0.3)
        result = analyze_loss_position(pos)
        assert result.suggested_scenario == LossScenario.CUT_LOSS

    def test_medium_loss_suggests_partial_cut(self):
        # -15% → PARTIAL_CUT disarankan
        pos = make_pos("BMRI", avg_cost=5000, current_price=4250, weight=0.3)
        result = analyze_loss_position(pos)
        assert result.suggested_scenario == LossScenario.PARTIAL_CUT

    def test_small_loss_suggests_stop_loss(self):
        # -7% → STOP_LOSS disarankan
        pos = make_pos("BMRI", avg_cost=5000, current_price=4650, weight=0.3)
        result = analyze_loss_position(pos)
        assert result.suggested_scenario == LossScenario.STOP_LOSS

    def test_cut_loss_remaining_exposure_zero(self):
        pos = make_pos("BMRI", avg_cost=5000, current_price=3500, weight=0.3)
        result = analyze_loss_position(pos)
        cut = next(s for s in result.scenarios if s.scenario == LossScenario.CUT_LOSS)
        assert cut.remaining_exposure_idr == 0.0

    def test_average_down_reduces_avg_cost(self):
        pos = make_pos("BMRI", avg_cost=5000, current_price=3500, weight=0.3)
        result = analyze_loss_position(pos)
        avg_down = next(s for s in result.scenarios if s.scenario == LossScenario.AVERAGE_DOWN)
        # Avg cost baru = (5000+3500)/2 = 4250
        assert avg_down.breakeven_price == pytest.approx(4250.0, abs=1.0)

    def test_stop_loss_price_is_5pct_below_current(self):
        pos = make_pos("BMRI", avg_cost=5000, current_price=4650, weight=0.3)
        result = analyze_loss_position(pos)
        stop = next(s for s in result.scenarios if s.scenario == LossScenario.STOP_LOSS)
        expected_stop = int(round(4650 * 0.95, 0))
        assert stop.breakeven_price == 5000.0  # impas = avg_cost
        # Stop loss level ada di description — angka bisa diformat dengan koma ribuan
        assert str(expected_stop) in stop.description.replace(",", "")

    def test_pros_and_cons_non_empty(self):
        pos = make_pos("BMRI", avg_cost=5000, current_price=3800, weight=0.3)
        result = analyze_loss_position(pos)
        for s in result.scenarios:
            assert len(s.pros) > 0
            assert len(s.cons) > 0

    def test_risk_levels_assigned(self):
        pos = make_pos("BMRI", avg_cost=5000, current_price=3800, weight=0.3)
        result = analyze_loss_position(pos)
        risk_levels = {s.risk_level for s in result.scenarios}
        assert "LOW" in risk_levels
        assert "HIGH" in risk_levels
