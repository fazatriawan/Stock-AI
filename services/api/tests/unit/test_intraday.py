"""
Unit tests FREE-09 — Intraday FreshnessStatus + market-close cleanup.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.ingestion.intraday import (
    is_idx_market_open,
    is_us_market_open,
    mark_intraday_stale,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wib(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Jakarta"))


def _est(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/New_York"))


# ---------------------------------------------------------------------------
# IDX market hours
# ---------------------------------------------------------------------------

class TestIsIdxMarketOpen:
    def test_open_morning_session(self):
        # Senin 09:30 WIB
        assert is_idx_market_open(_wib(2026, 11, 2, 9, 30).astimezone(timezone.utc)) is True

    def test_open_afternoon_session(self):
        # Senin 14:00 WIB
        assert is_idx_market_open(_wib(2026, 11, 2, 14, 0).astimezone(timezone.utc)) is True

    def test_closed_noon_break(self):
        # Senin 12:30 WIB — sesi istirahat siang
        assert is_idx_market_open(_wib(2026, 11, 2, 12, 30).astimezone(timezone.utc)) is False

    def test_closed_before_open(self):
        # Senin 08:59 WIB
        assert is_idx_market_open(_wib(2026, 11, 2, 8, 59).astimezone(timezone.utc)) is False

    def test_closed_after_afternoon(self):
        # Senin 15:50 WIB — tepat tutup
        assert is_idx_market_open(_wib(2026, 11, 2, 15, 50).astimezone(timezone.utc)) is False

    def test_closed_saturday(self):
        # Sabtu 10:00 WIB
        assert is_idx_market_open(_wib(2026, 11, 7, 10, 0).astimezone(timezone.utc)) is False

    def test_closed_sunday(self):
        # Minggu 10:00 WIB
        assert is_idx_market_open(_wib(2026, 11, 8, 10, 0).astimezone(timezone.utc)) is False

    def test_uses_utc_now_by_default(self):
        # Tanpa argumen tidak crash
        result = is_idx_market_open()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# US market hours
# ---------------------------------------------------------------------------

class TestIsUsMarketOpen:
    def test_open_mid_session(self):
        # Senin 11:00 EST
        assert is_us_market_open(_est(2026, 11, 2, 11, 0).astimezone(timezone.utc)) is True

    def test_closed_before_open(self):
        # Senin 09:00 EST — belum buka
        assert is_us_market_open(_est(2026, 11, 2, 9, 0).astimezone(timezone.utc)) is False

    def test_closed_after_close(self):
        # Senin 16:30 EST
        assert is_us_market_open(_est(2026, 11, 2, 16, 30).astimezone(timezone.utc)) is False

    def test_closed_saturday(self):
        # Sabtu 11:00 EST
        assert is_us_market_open(_est(2026, 11, 7, 11, 0).astimezone(timezone.utc)) is False

    def test_uses_utc_now_by_default(self):
        result = is_us_market_open()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# mark_intraday_stale
# ---------------------------------------------------------------------------

def _make_db(rowcount: int = 0) -> MagicMock:
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.rowcount = rowcount
    db.execute = AsyncMock(return_value=execute_result)
    return db


class TestMarkIntradayStale:
    @pytest.mark.asyncio
    async def test_returns_rowcount(self):
        db = _make_db(rowcount=7)
        count = await mark_intraday_stale(db)
        assert count == 7

    @pytest.mark.asyncio
    async def test_uses_today_by_default(self):
        db = _make_db(rowcount=0)
        count = await mark_intraday_stale(db)
        assert count == 0
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_custom_date(self):
        db = _make_db(rowcount=3)
        target = date(2026, 11, 1)
        count = await mark_intraday_stale(db, target_date=target)
        assert count == 3

    @pytest.mark.asyncio
    async def test_zero_when_no_intraday_bars(self):
        db = _make_db(rowcount=0)
        count = await mark_intraday_stale(db)
        assert count == 0

    @pytest.mark.asyncio
    async def test_calls_execute_once(self):
        db = _make_db(rowcount=5)
        await mark_intraday_stale(db)
        db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# AST: freshness_status disertakan di upsert intraday
# ---------------------------------------------------------------------------

class TestIntradayUpsertIncludesFreshness:
    def test_freshness_status_in_values_and_conflict(self):
        import ast
        import pathlib

        src = pathlib.Path(__file__).parent.parent.parent / "app" / "ingestion" / "intraday.py"
        tree = ast.parse(src.read_text())

        found_values = False
        found_conflict = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr == "values":
                for kw in node.keywords:
                    if kw.arg == "freshness_status":
                        found_values = True
            if func.attr == "on_conflict_do_update":
                for kw in node.keywords:
                    if kw.arg == "set_" and isinstance(kw.value, ast.Dict):
                        keys = [
                            k.s if isinstance(k, ast.Constant) else None
                            for k in kw.value.keys
                        ]
                        if "freshness_status" in keys:
                            found_conflict = True

        assert found_values, "freshness_status tidak ada di .values() upsert intraday"
        assert found_conflict, "freshness_status tidak ada di on_conflict_do_update set_"
