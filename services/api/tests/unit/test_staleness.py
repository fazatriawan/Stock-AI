"""
Unit tests FREE-07 — Staleness Marking Service.

Uji logika cutoff, idempoten, dan MarkStaleResponse schema.
mark_stale_bars diuji dengan mock DB ringan.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.staleness import (
    DEFAULT_STALENESS_DAYS,
    StalenessMarkResult,
    mark_stale_bars,
)


# ---------------------------------------------------------------------------
# Cutoff logic
# ---------------------------------------------------------------------------

class TestCutoffLogic:
    def test_cutoff_is_today_minus_days(self):
        """Cutoff = today - max_staleness_days."""
        today = date.today()
        expected = today - timedelta(days=3)
        # Cutoff sama dengan yang dihitung di mark_stale_bars
        from datetime import timedelta as td
        assert today - td(days=DEFAULT_STALENESS_DAYS) == expected

    def test_default_staleness_days(self):
        assert DEFAULT_STALENESS_DAYS == 3

    def test_staleness_mark_result_fields(self):
        from datetime import datetime, timezone
        r = StalenessMarkResult(
            marked_stale=5,
            cutoff_date=date(2024, 1, 10),
            instrument_id="BBCA",
            ran_at=datetime.now(tz=timezone.utc),
        )
        assert r.marked_stale == 5
        assert r.cutoff_date == date(2024, 1, 10)
        assert r.instrument_id == "BBCA"


# ---------------------------------------------------------------------------
# mark_stale_bars dengan mock DB
# ---------------------------------------------------------------------------

class TestMarkStaleBars:
    def _make_db(self, rowcount: int = 5) -> MagicMock:
        db = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = rowcount
        db.execute = AsyncMock(return_value=mock_result)
        return db

    @pytest.mark.asyncio
    async def test_returns_correct_count(self):
        db = self._make_db(rowcount=12)
        result = await mark_stale_bars(db, max_staleness_days=3)
        assert result.marked_stale == 12

    @pytest.mark.asyncio
    async def test_cutoff_in_result(self):
        db = self._make_db(rowcount=0)
        result = await mark_stale_bars(db, max_staleness_days=7)
        expected_cutoff = date.today() - timedelta(days=7)
        assert result.cutoff_date == expected_cutoff

    @pytest.mark.asyncio
    async def test_instrument_id_propagated(self):
        db = self._make_db(rowcount=3)
        result = await mark_stale_bars(db, max_staleness_days=3, instrument_id="abc-123")
        assert result.instrument_id == "abc-123"

    @pytest.mark.asyncio
    async def test_all_instruments_when_none(self):
        db = self._make_db(rowcount=100)
        result = await mark_stale_bars(db, max_staleness_days=3, instrument_id=None)
        assert result.instrument_id is None

    @pytest.mark.asyncio
    async def test_zero_rows_idempotent(self):
        """Jika tidak ada baris FRESH yang kadaluarsa, hasilnya 0 — tidak error."""
        db = self._make_db(rowcount=0)
        result = await mark_stale_bars(db, max_staleness_days=3)
        assert result.marked_stale == 0

    @pytest.mark.asyncio
    async def test_execute_called_once(self):
        db = self._make_db(rowcount=5)
        await mark_stale_bars(db, max_staleness_days=3)
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_ran_at_is_utc(self):
        from datetime import timezone
        db = self._make_db(rowcount=0)
        result = await mark_stale_bars(db, max_staleness_days=3)
        assert result.ran_at.tzinfo is not None


# ---------------------------------------------------------------------------
# mark_stale_from_policy — fallback ke default
# ---------------------------------------------------------------------------

class TestMarkStaleFromPolicy:
    @pytest.mark.asyncio
    async def test_uses_policy_days(self):
        """Harus memakai max_staleness_days dari policy."""
        from app.ingestion.staleness import mark_stale_from_policy

        db = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 7
        db.execute = AsyncMock(return_value=mock_result)

        mock_policy = MagicMock()
        mock_policy.max_staleness_days = 5

        with patch("app.ingestion.staleness.mark_stale_bars") as mock_fn:
            mock_fn.return_value = StalenessMarkResult(
                marked_stale=7,
                cutoff_date=date.today() - timedelta(days=5),
                instrument_id=None,
                ran_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )
            with patch("app.ingestion.staleness.get_or_create_default", new=AsyncMock(return_value=mock_policy)):
                result = await mark_stale_from_policy(db)

        mock_fn.assert_called_once_with(db, max_staleness_days=5, instrument_id=None)
        assert result.marked_stale == 7

    @pytest.mark.asyncio
    async def test_fallback_on_policy_error(self):
        """Jika policy gagal dibaca, fallback ke DEFAULT_STALENESS_DAYS."""
        from app.ingestion.staleness import mark_stale_from_policy

        db = MagicMock()

        with patch("app.ingestion.staleness.mark_stale_bars") as mock_fn:
            mock_fn.return_value = StalenessMarkResult(
                marked_stale=0,
                cutoff_date=date.today() - timedelta(days=DEFAULT_STALENESS_DAYS),
                instrument_id=None,
                ran_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )
            with patch("app.ingestion.staleness.get_or_create_default", side_effect=Exception("db error")):
                result = await mark_stale_from_policy(db)

        mock_fn.assert_called_once_with(db, max_staleness_days=DEFAULT_STALENESS_DAYS, instrument_id=None)


# ---------------------------------------------------------------------------
# MarkStaleResponse schema
# ---------------------------------------------------------------------------

class TestMarkStaleResponseSchema:
    def test_schema_fields(self):
        from app.api.schemas import MarkStaleResponse
        from datetime import datetime, timezone

        r = MarkStaleResponse(
            marked_stale=42,
            cutoff_date=date(2024, 1, 10),
            instrument_id=None,
            ran_at=datetime.now(tz=timezone.utc),
        )
        assert r.marked_stale == 42
        assert r.instrument_id is None

    def test_with_instrument_id(self):
        from app.api.schemas import MarkStaleResponse
        from datetime import datetime, timezone

        r = MarkStaleResponse(
            marked_stale=3,
            cutoff_date=date(2024, 1, 10),
            instrument_id="abc-uuid",
            ran_at=datetime.now(tz=timezone.utc),
        )
        assert r.instrument_id == "abc-uuid"
