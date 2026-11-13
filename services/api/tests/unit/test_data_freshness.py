"""
Unit tests FREE-06 — Freshness endpoint logic + PriceBar freshness field.

Uji logika perhitungan quality_pct, breakdown, edge case empty.
Endpoint diuji via konstruksi response langsung (tanpa DB asli).
"""
from __future__ import annotations

from datetime import date


# ---------------------------------------------------------------------------
# Helper: simulasi logika endpoint
# ---------------------------------------------------------------------------

def _compute_freshness(breakdown_raw: dict[str, int], last_bar: date | None, last_fresh: date | None):
    """Mirror kalkulasi di endpoint get_instrument_freshness."""
    total = sum(breakdown_raw.values())
    fresh = breakdown_raw.get("FRESH", 0)
    stale = breakdown_raw.get("STALE", 0)
    other = total - fresh - stale
    quality_pct = round(fresh / total * 100, 1) if total > 0 else 0.0
    return {
        "total": total,
        "fresh": fresh,
        "stale": stale,
        "other": other,
        "quality_pct": quality_pct,
        "last_bar": last_bar,
        "last_fresh": last_fresh,
    }


class TestFreshnessComputation:
    def test_all_fresh(self):
        r = _compute_freshness({"FRESH": 100}, date(2024, 1, 15), date(2024, 1, 15))
        assert r["total"] == 100
        assert r["fresh"] == 100
        assert r["stale"] == 0
        assert r["quality_pct"] == 100.0

    def test_mixed_statuses(self):
        r = _compute_freshness(
            {"FRESH": 80, "STALE": 15, "UNAVAILABLE": 5},
            date(2024, 1, 15),
            date(2024, 1, 10),
        )
        assert r["total"] == 100
        assert r["fresh"] == 80
        assert r["stale"] == 15
        assert r["other"] == 5
        assert r["quality_pct"] == 80.0

    def test_all_stale(self):
        r = _compute_freshness({"STALE": 50}, date(2023, 12, 31), None)
        assert r["quality_pct"] == 0.0
        assert r["last_fresh"] is None

    def test_empty_no_bars(self):
        r = _compute_freshness({}, None, None)
        assert r["total"] == 0
        assert r["quality_pct"] == 0.0

    def test_quality_pct_rounding(self):
        r = _compute_freshness({"FRESH": 1, "STALE": 2}, date(2024, 1, 3), date(2024, 1, 1))
        # 1/3 = 33.333... → 33.3
        assert r["quality_pct"] == 33.3

    def test_other_includes_all_non_fresh_stale(self):
        r = _compute_freshness(
            {"FRESH": 10, "STALE": 5, "QUOTA_EXHAUSTED": 3, "LICENSE_BLOCKED": 2},
            date(2024, 1, 10),
            date(2024, 1, 10),
        )
        assert r["other"] == 5  # 3 + 2


# ---------------------------------------------------------------------------
# PriceBarResponse default freshness field
# ---------------------------------------------------------------------------

class TestPriceBarResponseFreshness:
    def test_default_is_fresh(self):
        from app.api.schemas import PriceBarResponse
        from decimal import Decimal

        bar = PriceBarResponse(
            session_date=date(2024, 1, 15),
            open=None,
            high=None,
            low=None,
            close=100.0,
            adj_close=None,
            volume=None,
            provider="yfinance",
            is_adjusted=False,
        )
        assert bar.freshness_status == "FRESH"

    def test_explicit_stale(self):
        from app.api.schemas import PriceBarResponse

        bar = PriceBarResponse(
            session_date=date(2024, 1, 15),
            open=None,
            high=None,
            low=None,
            close=100.0,
            adj_close=None,
            volume=None,
            provider="yfinance",
            is_adjusted=False,
            freshness_status="STALE",
        )
        assert bar.freshness_status == "STALE"


# ---------------------------------------------------------------------------
# FreshnessBreakdown + InstrumentFreshnessResponse schema
# ---------------------------------------------------------------------------

class TestFreshnessSchemas:
    def test_breakdown_schema(self):
        from app.api.schemas import FreshnessBreakdown
        b = FreshnessBreakdown(status="FRESH", count=42)
        assert b.status == "FRESH"
        assert b.count == 42

    def test_instrument_freshness_response(self):
        from app.api.schemas import FreshnessBreakdown, InstrumentFreshnessResponse
        r = InstrumentFreshnessResponse(
            instrument_id="BBCA",
            total_bars=100,
            fresh_bars=90,
            stale_bars=10,
            other_bars=0,
            data_quality_pct=90.0,
            last_fresh_date=date(2024, 1, 15),
            last_bar_date=date(2024, 1, 15),
            breakdown=[FreshnessBreakdown(status="FRESH", count=90)],
        )
        assert r.data_quality_pct == 90.0
        assert len(r.breakdown) == 1

    def test_no_dates_allowed(self):
        from app.api.schemas import InstrumentFreshnessResponse
        r = InstrumentFreshnessResponse(
            instrument_id="X",
            total_bars=0,
            fresh_bars=0,
            stale_bars=0,
            other_bars=0,
            data_quality_pct=0.0,
            breakdown=[],
        )
        assert r.last_fresh_date is None
        assert r.last_bar_date is None


# ---------------------------------------------------------------------------
# ohlcv.py includes freshness_status=FRESH on insert
# ---------------------------------------------------------------------------

class TestOHLCVIngestFreshnessField:
    """Verifikasi bahwa kamus yang diinsert ke DB menyertakan freshness_status."""

    def test_insert_dict_has_freshness(self):
        """
        Baca source ohlcv.py dan pastikan freshness_status ada di to_insert.
        """
        import ast
        import pathlib

        src = pathlib.Path(__file__).parent.parent.parent / "app" / "ingestion" / "ohlcv.py"
        tree = ast.parse(src.read_text())

        # Cari semua dict literal di dalam to_insert.append(...)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "append":
                    for arg in node.args:
                        if isinstance(arg, ast.Dict):
                            keys = [
                                k.s if isinstance(k, ast.Constant) else None
                                for k in arg.keys
                            ]
                            if "freshness_status" in keys:
                                found = True
        assert found, "freshness_status tidak ditemukan di to_insert dict di ohlcv.py"
