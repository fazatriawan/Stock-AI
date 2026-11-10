"""Unit tests untuk Decision & Portfolio Attribution Engine (HARD-05 / R18)."""
from app.analytics.attribution import (
    PositionAttributionInput,
    compute_portfolio_attribution,
    compute_position_attribution,
)


def test_single_position_attribution_math() -> None:
    inp = PositionAttributionInput(
        symbol="IDX:BBCA",
        sector="Financials",
        gross_cost=10_000_000.0,
        total_cost=10_015_000.0,  # Rp15.000 fee
        market_value=11_500_000.0,
        dividend_received=300_000.0,
        benchmark_return_pct=5.0,
        sector_return_pct=8.0,
    )
    res = compute_position_attribution(inp, weight=1.0)
    assert res.price_return_pct > 14.0
    assert res.dividend_contribution_pct > 2.9
    assert res.cost_drag_pct < 0.0
    assert res.benchmark_effect_pct == 5.0
    assert res.sector_excess_pct == 3.0  # 8% - 5%
    assert res.stock_specific_alpha_pct == 7.0  # 15% gross - 8% sector
    assert res.baseline_excess_pct > 12.0


def test_empty_portfolio_attribution() -> None:
    report = compute_portfolio_attribution([], benchmark_return_pct=4.5)
    assert report.portfolio_total_return_pct == 0.0
    assert report.benchmark_return_pct == 4.5
    assert report.portfolio_excess_return_pct == -4.5
    assert report.positions == []


def test_multi_position_weighted_attribution() -> None:
    inputs = [
        PositionAttributionInput(
            symbol="IDX:BMRI",
            sector="Financials",
            gross_cost=5_000_000.0,
            total_cost=5_000_000.0,
            market_value=6_000_000.0,  # +20%
            dividend_received=250_000.0,  # +5% -> total +25%
            benchmark_return_pct=5.0,
            sector_return_pct=10.0,
        ),
        PositionAttributionInput(
            symbol="IDX:TLKM",
            sector="Telecoms",
            gross_cost=5_000_000.0,
            total_cost=5_000_000.0,
            market_value=5_250_000.0,  # +5%
            dividend_received=0.0,
            benchmark_return_pct=5.0,
            sector_return_pct=2.0,
        ),
    ]
    report = compute_portfolio_attribution(inputs, benchmark_return_pct=5.0)
    assert len(report.positions) == 2
    # Equal weights (0.5 each): 0.5 * 25% + 0.5 * 5% = 15.0%
    assert report.portfolio_total_return_pct == 15.0
    assert report.portfolio_excess_return_pct == 10.0
    assert report.weighted_dividend_pct == 2.5
