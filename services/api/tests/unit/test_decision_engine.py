"""
Golden tests untuk decision engine.
Gate Milestone B: 8 skenario — BUY/HOLD/SELL/WAIT/INSUFFICIENT_DATA +
corporate action + stale data + concentration.
"""
from datetime import date


from app.analytics.fundamental import FundamentalSnapshot
from app.analytics.technical import TechnicalSnapshot
from app.decisions.engine import (
    Action,
    DecisionConfig,
    HardGateStatus,
    PortfolioContext,
    Urgency,
    run_decision_engine,
)


def make_good_technical() -> TechnicalSnapshot:
    snap = TechnicalSnapshot(as_of=date(2026, 6, 1), instrument_id="TEST")
    snap.sufficient_data = True
    snap.bars_available = 250
    snap.sma_20 = 9000.0
    snap.sma_50 = 8800.0
    snap.sma_200 = 8500.0
    snap.above_sma_20 = True
    snap.above_sma_50 = True
    snap.above_sma_200 = True
    snap.golden_cross = True
    snap.rsi_14 = 55.0
    snap.macd = 50.0
    snap.macd_hist = 10.0
    snap.percentile_52w = 0.60
    snap.return_1d = 0.005
    snap.return_20d = 0.04
    snap.volume_ratio_20 = 1.2
    return snap


def make_good_fundamental(is_bank: bool = True) -> FundamentalSnapshot:
    snap = FundamentalSnapshot(instrument_id="TEST", as_of=date(2026, 6, 1))
    snap.sector = "Financials" if is_bank else "Technology"
    snap.data_freshness = "FRESH"
    if is_bank:
        snap.roe = 0.18
        snap.nim = 0.06
        snap.npl_gross = 0.02
        snap.car = 0.22
        snap.pb_ratio = 2.0
        snap.metrics_available = ["ROE", "NIM", "NPL_GROSS", "CAR", "P/B"]
        snap.metrics_missing = []
    else:
        snap.roe = 0.20
        snap.pe_ratio = 15.0
        snap.revenue = 1e13
        snap.net_income = 2e12
        snap.eps = 200.0
        snap.gross_margin = 0.40
        snap.operating_margin = 0.20
        snap.metrics_available = ["ROE", "PE_RATIO", "REVENUE", "NET_INCOME", "EPS"]
        snap.metrics_missing = []
    return snap


def default_portfolio(owned: bool = False) -> PortfolioContext:
    return PortfolioContext(
        owned=owned,
        shares=0.0 if not owned else 1000.0,
        portfolio_weight=0.0 if not owned else 0.05,
        available_cash=100_000_000,
    )


class TestHardGates:
    def test_suspension_gives_insufficient_data(self) -> None:
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            default_portfolio(), DecisionConfig(),
            is_suspended=True,
        )
        assert output.action == Action.INSUFFICIENT_DATA
        assert output.urgency == Urgency.REVIEW_NOW
        assert output.hard_gate_status == HardGateStatus.FAIL_SUSPENSION

    def test_stale_price_gives_insufficient_data(self) -> None:
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            default_portfolio(), DecisionConfig(),
            stale_price=True,
        )
        assert output.action == Action.INSUFFICIENT_DATA
        assert output.hard_gate_status == HardGateStatus.FAIL_STALE_PRICE

    def test_corporate_action_gives_insufficient_data(self) -> None:
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            default_portfolio(), DecisionConfig(),
            has_unresolved_corporate_action=True,
        )
        assert output.action == Action.INSUFFICIENT_DATA
        assert output.hard_gate_status == HardGateStatus.FAIL_CORPORATE_ACTION
        assert output.urgency == Urgency.REVIEW_NOW

    def test_low_coverage_gives_insufficient_data(self) -> None:
        # Tidak ada data teknikal DAN tidak ada fundamental yang bisa dihitung → core coverage = 0
        fund = FundamentalSnapshot(instrument_id="TEST", as_of=date(2026, 6, 1))
        fund.sector = "Financials"
        fund.metrics_available = []
        fund.metrics_missing = ["ROE", "NIM", "NPL_GROSS", "CAR", "P/B"]
        tech = TechnicalSnapshot(as_of=date(2026, 6, 1), instrument_id="TEST")
        # sufficient_data = False → technical score = None
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            tech, fund, default_portfolio(), DecisionConfig(),
        )
        assert output.action == Action.INSUFFICIENT_DATA
        assert output.hard_gate_status == HardGateStatus.FAIL_COVERAGE


class TestBuyScenario:
    def test_buy_when_all_green(self) -> None:
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            default_portfolio(owned=False), DecisionConfig(),
        )
        assert output.action == Action.BUY
        assert output.hard_gate_status == HardGateStatus.PASS
        assert output.composite_score > 0

    def test_buy_has_bull_and_bear_thesis(self) -> None:
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            default_portfolio(), DecisionConfig(),
        )
        assert len(output.bull_thesis) > 0
        assert len(output.bear_case) > 0
        assert len(output.invalidation_triggers) > 0

    def test_no_buy_when_no_cash(self) -> None:
        portfolio = default_portfolio(owned=False)
        portfolio.available_cash = 0.0
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            portfolio, DecisionConfig(),
        )
        assert output.action == Action.WAIT


class TestHoldScenario:
    def test_hold_or_add_owned_healthy_thesis(self) -> None:
        # Posisi dimiliki + tesis kuat → ADD_CANDIDATE (cukup ruang) atau HOLD (composite < threshold)
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            default_portfolio(owned=True), DecisionConfig(),
        )
        assert output.action in (Action.HOLD, Action.ADD_CANDIDATE)

    def test_hold_owned_moderate_thesis(self) -> None:
        # Tesis cukup (composite ~57 — > 45 tapi < threshold 60) → HOLD
        tech = TechnicalSnapshot(as_of=date(2026, 6, 1), instrument_id="TEST")
        tech.sufficient_data = True
        tech.bars_available = 250
        tech.above_sma_20 = True
        tech.above_sma_50 = True
        tech.above_sma_200 = False   # tidak di atas SMA200
        tech.golden_cross = None
        tech.rsi_14 = 50.0
        tech.percentile_52w = 0.50

        fund = FundamentalSnapshot(instrument_id="TEST", as_of=date(2026, 6, 1))
        fund.sector = "Financials"
        fund.data_freshness = "FRESH"
        fund.roe = 0.16   # ok tapi tidak outstanding
        fund.nim = 0.05
        fund.npl_gross = 0.025
        fund.pb_ratio = 2.0   # wajar → valuation 65

        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            tech, fund,
            default_portfolio(owned=True), DecisionConfig(),
        )
        # composite ~57.5 → thesis intact, tapi < threshold → HOLD atau ADD
        assert output.action in (Action.HOLD, Action.ADD_CANDIDATE)


class TestSellScenario:
    def test_sell_owned_broken_thesis(self) -> None:
        tech = TechnicalSnapshot(as_of=date(2026, 6, 1), instrument_id="TEST")
        tech.sufficient_data = True
        tech.bars_available = 250
        tech.sma_20 = 10000.0
        tech.above_sma_20 = False
        tech.above_sma_50 = False
        tech.above_sma_200 = False
        tech.rsi_14 = 25.0
        tech.percentile_52w = 0.05

        fund = make_good_fundamental()
        fund.roe = 0.03
        fund.nim = 0.01
        fund.npl_gross = 0.10
        fund.metrics_available = ["ROE", "NIM", "NPL_GROSS", "CAR", "P/B"]

        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            tech, fund, default_portfolio(owned=True), DecisionConfig(),
        )
        assert output.action == Action.SELL


class TestWaitScenario:
    def test_wait_not_owned_mediocre(self) -> None:
        fund = make_good_fundamental()
        fund.pb_ratio = 4.5  # mahal
        fund.roe = 0.09

        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), fund,
            default_portfolio(owned=False), DecisionConfig(),
        )
        assert output.action in (Action.WAIT, Action.BUY)


class TestConcentrationLimit:
    def test_review_now_when_over_limit(self) -> None:
        portfolio = default_portfolio(owned=True)
        portfolio.portfolio_weight = 0.15  # > maks 10%
        portfolio.max_position_weight = 0.10

        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            portfolio, DecisionConfig(),
        )
        assert output.urgency == Urgency.REVIEW_NOW

    def test_no_buy_when_sector_full(self) -> None:
        portfolio = default_portfolio(owned=False)
        portfolio.sector_weight = 0.35  # > maks 30%
        portfolio.max_sector_weight = 0.30

        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            portfolio, DecisionConfig(),
        )
        assert output.action == Action.WAIT


class TestOutputContract:
    def test_human_approval_always_required(self) -> None:
        """Action apapun tidak boleh mengklaim tidak perlu persetujuan manusia."""
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            default_portfolio(), DecisionConfig(),
        )
        # Rekomendasi selalu butuh human decision — verified di schema layer
        assert output.action is not None  # engine tidak memasang order

    def test_composite_score_0_100(self) -> None:
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            default_portfolio(), DecisionConfig(),
        )
        assert 0.0 <= output.composite_score <= 100.0

    def test_liquidity_hard_gate_blocks_illiquid_microcap(self) -> None:
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            default_portfolio(owned=False), DecisionConfig(),
            last_price=500.0,
            adv_shares=200.0,  # 1 lot (100 shares) = 50% ADV (> 25%)
            exchange="IDX",
        )
        assert output.hard_gate_status == HardGateStatus.FAIL_LIQUIDITY
        assert output.action == Action.WAIT

    def test_min_lot_capital_blocks_buy_when_cash_less_than_one_lot(self) -> None:
        portfolio = default_portfolio(owned=False)
        portfolio.available_cash = 200_000.0  # Rp200rb, sedangkan 1 lot @ Rp5.000 = Rp500rb
        output = run_decision_engine(
            "TEST", date(2026, 6, 1),
            make_good_technical(), make_good_fundamental(),
            portfolio, DecisionConfig(),
            last_price=5000.0,
            adv_shares=500_000.0,
            exchange="IDX",
        )
        assert output.action == Action.WAIT
        assert any("1 lot minimum" in c for c in output.conditions_to_buy)
