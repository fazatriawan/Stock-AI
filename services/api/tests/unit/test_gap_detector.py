"""
Unit tests FREE-17 — Data gap detector.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analytics.gap_detector import (
    _business_days,
    _classify,
    detect_data_gaps,
)


# ---------------------------------------------------------------------------
# _business_days helper
# ---------------------------------------------------------------------------

class TestBusinessDays:
    def test_single_weekday(self):
        # Monday
        d = date(2026, 11, 2)
        assert _business_days(d, d) == 1

    def test_one_full_week(self):
        # Mon to Sun = 5 business days
        assert _business_days(date(2026, 11, 2), date(2026, 11, 8)) == 5

    def test_two_weeks(self):
        assert _business_days(date(2026, 11, 2), date(2026, 11, 15)) == 10

    def test_weekend_only(self):
        # Sat to Sun = 0 business days
        assert _business_days(date(2026, 11, 7), date(2026, 11, 8)) == 0

    def test_one_year_approx(self):
        bdays = _business_days(date(2025, 1, 1), date(2025, 12, 31))
        # ~261 hari kerja dalam setahun (2025 bukan kabisat)
        assert 255 <= bdays <= 265

    def test_same_day_friday(self):
        assert _business_days(date(2026, 11, 6), date(2026, 11, 6)) == 1


# ---------------------------------------------------------------------------
# _classify helper
# ---------------------------------------------------------------------------

class TestClassify:
    def test_ok(self):
        assert _classify(0.0) == "OK"
        assert _classify(9.9) == "OK"

    def test_warning(self):
        assert _classify(10.0) == "WARNING"
        assert _classify(24.9) == "WARNING"

    def test_critical(self):
        assert _classify(25.0) == "CRITICAL"
        assert _classify(99.9) == "CRITICAL"


# ---------------------------------------------------------------------------
# detect_data_gaps — mock DB
# ---------------------------------------------------------------------------

def _make_db_with_data(agg_data, instr_data):
    """
    agg_data: list of (instrument_id, bar_count, first_date, last_date)
    instr_data: list of (id, canonical_symbol, exchange)
    """
    db = MagicMock()

    agg_rows = []
    for iid, count, first, last in agg_data:
        row = MagicMock()
        row.instrument_id = iid
        row.bar_count = count
        row.first_date = first
        row.last_date = last
        agg_rows.append(row)

    instr_rows = []
    for iid, sym, exch in instr_data:
        row = MagicMock()
        row.id = iid
        row.canonical_symbol = sym
        row.exchange = exch
        instr_rows.append(row)

    agg_result = MagicMock()
    agg_result.__iter__ = MagicMock(return_value=iter(agg_rows))

    instr_result = MagicMock()
    instr_result.__iter__ = MagicMock(return_value=iter(instr_rows))

    db.execute = AsyncMock(side_effect=[agg_result, instr_result])
    return db


class TestDetectDataGaps:
    @pytest.mark.asyncio
    async def test_empty_db_returns_zero(self):
        db = MagicMock()
        empty_result = MagicMock()
        empty_result.__iter__ = MagicMock(return_value=iter([]))
        db.execute = AsyncMock(return_value=empty_result)

        result = await detect_data_gaps(db)
        assert result.instruments_checked == 0
        assert result.reports == []

    @pytest.mark.asyncio
    async def test_no_gap_instrument_excluded(self):
        """Instrumen dengan data lengkap tidak masuk laporan."""
        # 1 tahun data, bar_count ≈ 252 (cukup untuk 90% hari kerja)
        agg = [("id-1", 240, date(2024, 1, 2), date(2024, 12, 31))]
        instr = [("id-1", "IDX:BBCA", "IDX")]
        db = _make_db_with_data(agg, instr)

        result = await detect_data_gaps(db, threshold_pct=10.0)
        # gap_pct harus kecil (< 10%), instrumen tidak masuk laporan
        assert all(r.canonical_symbol != "IDX:BBCA" for r in result.reports)

    @pytest.mark.asyncio
    async def test_large_gap_instrument_reported(self):
        """Instrumen dengan 50% bar hilang pasti masuk CRITICAL."""
        # 1 tahun history, hanya 100 bar (expected ~230)
        agg = [("id-2", 100, date(2024, 1, 2), date(2024, 12, 31))]
        instr = [("id-2", "IDX:BMRI", "IDX")]
        db = _make_db_with_data(agg, instr)

        result = await detect_data_gaps(db, threshold_pct=10.0)
        assert len(result.reports) == 1
        r = result.reports[0]
        assert r.canonical_symbol == "IDX:BMRI"
        assert r.severity == "CRITICAL"
        assert r.gap_pct > 25.0

    @pytest.mark.asyncio
    async def test_short_history_excluded(self):
        """Instrumen dengan history < min_days_history diabaikan."""
        agg = [("id-3", 5, date(2026, 11, 1), date(2026, 11, 10))]
        instr = [("id-3", "IDX:TLKM", "IDX")]
        db = _make_db_with_data(agg, instr)

        result = await detect_data_gaps(db, min_days_history=30)
        assert result.reports == []

    @pytest.mark.asyncio
    async def test_sorted_by_gap_pct_desc(self):
        """Laporan diurutkan gap_pct tertinggi di atas."""
        agg = [
            ("id-a", 20, date(2024, 1, 2), date(2024, 12, 31)),   # gap besar
            ("id-b", 200, date(2024, 1, 2), date(2024, 12, 31)),  # gap kecil
        ]
        instr = [
            ("id-a", "IDX:AALI", "IDX"),
            ("id-b", "IDX:ADRO", "IDX"),
        ]
        db = _make_db_with_data(agg, instr)

        result = await detect_data_gaps(db, threshold_pct=5.0)
        if len(result.reports) >= 2:
            assert result.reports[0].gap_pct >= result.reports[1].gap_pct

    @pytest.mark.asyncio
    async def test_instruments_checked_counts_all(self):
        agg = [
            ("id-x", 240, date(2024, 1, 2), date(2024, 12, 31)),
            ("id-y", 50, date(2024, 1, 2), date(2024, 12, 31)),
        ]
        instr = [
            ("id-x", "IDX:X", "IDX"),
            ("id-y", "IDX:Y", "IDX"),
        ]
        db = _make_db_with_data(agg, instr)

        result = await detect_data_gaps(db, threshold_pct=10.0)
        assert result.instruments_checked == 2

    @pytest.mark.asyncio
    async def test_limit_applied(self):
        """Hanya 2 instrumen terburuk dilaporkan jika limit=2."""
        agg = [(f"id-{i}", 10, date(2024, 1, 2), date(2024, 12, 31)) for i in range(5)]
        instr = [(f"id-{i}", f"IDX:SYM{i}", "IDX") for i in range(5)]
        db = _make_db_with_data(agg, instr)

        result = await detect_data_gaps(db, threshold_pct=5.0, limit=2)
        assert len(result.reports) <= 2

    @pytest.mark.asyncio
    async def test_with_gaps_counts_non_ok(self):
        agg = [
            ("id-1", 10, date(2024, 1, 2), date(2024, 12, 31)),   # critical
            ("id-2", 50, date(2024, 1, 2), date(2024, 12, 31)),   # warning
        ]
        instr = [
            ("id-1", "IDX:A", "IDX"),
            ("id-2", "IDX:B", "IDX"),
        ]
        db = _make_db_with_data(agg, instr)

        result = await detect_data_gaps(db, threshold_pct=5.0)
        assert result.with_gaps == sum(1 for r in result.reports if r.severity != "OK")


# ---------------------------------------------------------------------------
# AST check: api.ts + settings page
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_data_gaps_status_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "DataGapsStatus" in content
        assert "GapReportRow" in content
        assert "api.data.gaps" in content or "gaps:" in content

    def test_data_gaps_section_in_settings(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "settings" / "page.tsx"
        if not src.exists():
            pytest.skip("settings/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "DataGapsSection" in content
        assert "SeverityBadge" in content
