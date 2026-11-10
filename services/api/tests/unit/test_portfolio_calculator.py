"""
Unit test untuk portfolio calculator — WAC (Weighted Average Cost).
Tes accounting harus deterministik dan tidak bergantung pada DB atau AI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pytest

from app.portfolio.calculator import (
    compute_positions,
    enrich_positions_with_prices,
)


# ---------------------------------------------------------------------------
# Fake Trade untuk test (tidak butuh DB)
# ---------------------------------------------------------------------------

@dataclass
class FakeTrade:
    """Minimal trade object yang cocok dengan interface compute_positions."""
    id: str
    instrument_id: str
    trade_date: date
    side: str
    shares: float
    price: float
    fee: float = 0.0
    tax: float = 0.0
    portfolio_id: str = "portfolio-1"
    currency: str = "IDR"
    source_broker: Optional[str] = None
    import_fingerprint: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Tests: single position
# ---------------------------------------------------------------------------

class TestSingleBuy:
    def test_basic_buy(self):
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 1000, 5000.0)
        ]
        positions = compute_positions(trades)
        assert "instr-A" in positions
        pos = positions["instr-A"]
        assert pos.shares == 1000.0
        assert pos.lots == 10.0  # 1000 / 100
        assert pos.avg_cost == pytest.approx(5000.0)
        assert pos.total_cost == pytest.approx(5_000_000.0)

    def test_buy_with_fee(self):
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0, fee=2500.0)
        ]
        positions = compute_positions(trades)
        pos = positions["instr-A"]
        # avg_cost = (100 * 5000 + 2500) / 100 = 5025
        assert pos.avg_cost == pytest.approx(5025.0)
        assert pos.total_cost == pytest.approx(502_500.0)

    def test_trade_count(self):
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0),
            FakeTrade("t2", "instr-A", date(2024, 2, 1), "BUY", 100, 5200.0),
        ]
        positions = compute_positions(trades)
        assert positions["instr-A"].trade_count == 2


class TestMultipleBuys:
    def test_wac_two_buys(self):
        """Pembelian kedua dengan harga berbeda harus menghasilkan rata-rata tertimbang."""
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 4000.0),
            FakeTrade("t2", "instr-A", date(2024, 3, 1), "BUY", 100, 6000.0),
        ]
        positions = compute_positions(trades)
        pos = positions["instr-A"]
        assert pos.shares == 200.0
        # WAC = (100*4000 + 100*6000) / 200 = 5000
        assert pos.avg_cost == pytest.approx(5000.0)
        assert pos.total_cost == pytest.approx(1_000_000.0)

    def test_wac_three_buys(self):
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 1), "BUY", 100, 3000.0),
            FakeTrade("t2", "instr-A", date(2024, 2, 1), "BUY", 200, 4000.0),
            FakeTrade("t3", "instr-A", date(2024, 3, 1), "BUY", 300, 5000.0),
        ]
        positions = compute_positions(trades)
        pos = positions["instr-A"]
        assert pos.shares == 600.0
        # WAC = (100*3000 + 200*4000 + 300*5000) / 600 = (300k+800k+1500k)/600 = 2600k/600 = 4333.33
        expected_avg = (100*3000 + 200*4000 + 300*5000) / 600
        assert pos.avg_cost == pytest.approx(expected_avg, rel=1e-5)


class TestBuySell:
    def test_partial_sell_keeps_avg_cost(self):
        """WAC: jual sebagian tidak mengubah avg_cost."""
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 1000, 5000.0),
            FakeTrade("t2", "instr-A", date(2024, 6, 1), "SELL", 500, 6000.0),
        ]
        positions = compute_positions(trades)
        pos = positions["instr-A"]
        assert pos.shares == 500.0
        assert pos.avg_cost == pytest.approx(5000.0)  # avg_cost tidak berubah
        assert pos.total_cost == pytest.approx(500 * 5000.0)

    def test_full_sell_removes_position(self):
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0),
            FakeTrade("t2", "instr-A", date(2024, 6, 1), "SELL", 100, 6000.0),
        ]
        positions = compute_positions(trades)
        assert "instr-A" not in positions

    def test_buy_after_sell(self):
        """Beli lagi setelah jual semua — avg_cost baru dihitung dari awal."""
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0),
            FakeTrade("t2", "instr-A", date(2024, 6, 1), "SELL", 100, 6000.0),
            FakeTrade("t3", "instr-A", date(2024, 9, 1), "BUY", 100, 4500.0),
        ]
        positions = compute_positions(trades)
        pos = positions["instr-A"]
        assert pos.shares == 100.0
        assert pos.avg_cost == pytest.approx(4500.0)  # harga beli terbaru


# ---------------------------------------------------------------------------
# Tests: multiple instruments
# ---------------------------------------------------------------------------

class TestMultipleInstruments:
    def test_two_instruments_independent(self):
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0),
            FakeTrade("t2", "instr-B", date(2024, 1, 5), "BUY", 200, 3000.0),
        ]
        positions = compute_positions(trades)
        assert len(positions) == 2
        assert positions["instr-A"].avg_cost == pytest.approx(5000.0)
        assert positions["instr-B"].avg_cost == pytest.approx(3000.0)
        assert positions["instr-A"].shares == 100.0
        assert positions["instr-B"].shares == 200.0


# ---------------------------------------------------------------------------
# Tests: point-in-time
# ---------------------------------------------------------------------------

class TestPointInTime:
    def test_as_of_excludes_future_trades(self):
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0),
            FakeTrade("t2", "instr-A", date(2024, 6, 1), "BUY", 100, 6000.0),
        ]
        # As of Jan 31 — hanya trade pertama yang masuk
        positions = compute_positions(trades, as_of=date(2024, 1, 31))
        pos = positions["instr-A"]
        assert pos.shares == 100.0
        assert pos.avg_cost == pytest.approx(5000.0)

    def test_as_of_includes_trades_on_date(self):
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0),
        ]
        positions = compute_positions(trades, as_of=date(2024, 1, 2))
        assert "instr-A" in positions


# ---------------------------------------------------------------------------
# Tests: seed data dari CR §10
# ---------------------------------------------------------------------------

class TestCRSeedData:
    """Validasi hitungan untuk portofolio awal yang di-seed dari CR §10."""

    def _seed_trades(self) -> list:
        return [
            FakeTrade("s1", "IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4978.69),  # 11 lot
            FakeTrade("s2", "IDX:BBRI", date(2024, 1, 2), "BUY", 1400, 2978.05),  # 14 lot
            FakeTrade("s3", "IDX:BBNI", date(2024, 1, 2), "BUY",  300, 3375.89),  # 3 lot
            FakeTrade("s4", "IDX:BBCA", date(2024, 1, 2), "BUY",  100, 4978.69),  # 1 lot
        ]

    def test_four_positions(self):
        positions = compute_positions(self._seed_trades())
        assert len(positions) == 4

    def test_bmri_lots(self):
        positions = compute_positions(self._seed_trades())
        assert positions["IDX:BMRI"].lots == pytest.approx(11.0)

    def test_bbca_lots(self):
        positions = compute_positions(self._seed_trades())
        assert positions["IDX:BBCA"].lots == pytest.approx(1.0)

    def test_total_invested(self):
        positions = compute_positions(self._seed_trades())
        total = sum(p.total_cost for p in positions.values())
        # BMRI: 1100 * 4978.69 = 5476559
        # BBRI: 1400 * 2978.05 = 4169270
        # BBNI: 300 * 3375.89 = 1012767
        # BBCA: 100 * 4978.69 = 497869
        expected = 1100 * 4978.69 + 1400 * 2978.05 + 300 * 3375.89 + 100 * 4978.69
        assert total == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# Tests: enrich_positions_with_prices
# ---------------------------------------------------------------------------

class TestEnrichWithPrices:
    def test_unrealized_pnl_profit(self):
        trades = [FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0)]
        positions = compute_positions(trades)
        prices = {"instr-A": (6000.0, date(2024, 11, 1))}
        positions = enrich_positions_with_prices(positions, prices)
        pos = positions["instr-A"]
        assert pos.market_value == pytest.approx(600_000.0)
        assert pos.unrealized_pnl == pytest.approx(100_000.0)
        assert pos.unrealized_pnl_pct == pytest.approx(0.20, rel=1e-4)

    def test_unrealized_pnl_loss(self):
        trades = [FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0)]
        positions = compute_positions(trades)
        prices = {"instr-A": (4000.0, date(2024, 11, 1))}
        positions = enrich_positions_with_prices(positions, prices)
        pos = positions["instr-A"]
        assert pos.unrealized_pnl == pytest.approx(-100_000.0)
        assert pos.unrealized_pnl_pct == pytest.approx(-0.20, rel=1e-4)

    def test_weight_calculation(self):
        trades = [
            FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0),
            FakeTrade("t2", "instr-B", date(2024, 1, 2), "BUY", 100, 5000.0),
        ]
        positions = compute_positions(trades)
        prices = {
            "instr-A": (5000.0, date(2024, 11, 1)),
            "instr-B": (5000.0, date(2024, 11, 1)),
        }
        positions = enrich_positions_with_prices(positions, prices)
        # Masing-masing harus 50% dari total
        assert positions["instr-A"].weight == pytest.approx(0.5, rel=1e-4)
        assert positions["instr-B"].weight == pytest.approx(0.5, rel=1e-4)

    def test_no_price_no_pnl(self):
        trades = [FakeTrade("t1", "instr-A", date(2024, 1, 2), "BUY", 100, 5000.0)]
        positions = compute_positions(trades)
        positions = enrich_positions_with_prices(positions, {})
        pos = positions["instr-A"]
        assert pos.market_value is None
        assert pos.unrealized_pnl is None
