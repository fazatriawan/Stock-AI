"""
Unit tests FREE-12 — Empty-ingest classifier + UNAVAILABLE / QUOTA_EXHAUSTED marking.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ingestion.empty_ingest import classify_empty_ingest, mark_empty_bars


# ---------------------------------------------------------------------------
# classify_empty_ingest
# ---------------------------------------------------------------------------

class TestClassifyEmptyIngest:
    def test_no_error_no_data_is_unavailable(self):
        result = classify_empty_ingest("IDX:XXXX", error=None)
        assert result == "UNAVAILABLE"

    def test_no_data_found_message_is_unavailable(self):
        err = Exception("No data found for XXXX")
        result = classify_empty_ingest("IDX:XXXX", error=err)
        assert result == "UNAVAILABLE"

    def test_delisted_message_is_unavailable(self):
        err = Exception("Symbol may be delisted")
        result = classify_empty_ingest("US:XXXX", error=err)
        assert result == "UNAVAILABLE"

    def test_no_timezone_found_is_unavailable(self):
        err = Exception("No timezone found for symbol ZZZZ.JK")
        result = classify_empty_ingest("IDX:ZZZZ", error=err)
        assert result == "UNAVAILABLE"

    def test_invalid_ticker_is_unavailable(self):
        err = Exception("invalid ticker FAKE")
        result = classify_empty_ingest("US:FAKE", error=err)
        assert result == "UNAVAILABLE"

    def test_too_many_requests_is_quota_exhausted(self):
        err = Exception("Too Many Requests - rate limit exceeded")
        result = classify_empty_ingest("IDX:BBCA", error=err)
        assert result == "QUOTA_EXHAUSTED"

    def test_429_in_message_is_quota_exhausted(self):
        err = Exception("HTTP 429: quota exceeded for free tier")
        result = classify_empty_ingest("US:AAPL", error=err)
        assert result == "QUOTA_EXHAUSTED"

    def test_throttled_is_quota_exhausted(self):
        err = Exception("Request throttled by upstream server")
        result = classify_empty_ingest("IDX:BBRI", error=err)
        assert result == "QUOTA_EXHAUSTED"

    def test_network_error_stays_stale(self):
        err = ConnectionError("Connection reset by peer")
        result = classify_empty_ingest("IDX:TLKM", error=err)
        assert result == "STALE"

    def test_timeout_stays_stale(self):
        err = TimeoutError("Request timed out after 30s")
        result = classify_empty_ingest("US:MSFT", error=err)
        assert result == "STALE"

    def test_quota_takes_priority_over_unavailable(self):
        # Jika pesan mengandung "rate limit" sekaligus kata "not found" → quota menang
        err = Exception("rate limit: not found in quota pool")
        result = classify_empty_ingest("IDX:BBCA", error=err)
        assert result == "QUOTA_EXHAUSTED"

    def test_case_insensitive_matching(self):
        err = Exception("NO DATA FOUND FOR SYMBOL")
        result = classify_empty_ingest("IDX:ABCD", error=err)
        assert result == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# mark_empty_bars
# ---------------------------------------------------------------------------

def _make_db(rowcount: int = 0) -> MagicMock:
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.rowcount = rowcount
    db.execute = AsyncMock(return_value=execute_result)
    return db


class TestMarkEmptyBars:
    @pytest.mark.asyncio
    async def test_marks_stale_as_unavailable(self):
        db = _make_db(rowcount=5)
        count = await mark_empty_bars(db, "uuid-abc", "UNAVAILABLE")
        assert count == 5

    @pytest.mark.asyncio
    async def test_marks_stale_as_quota_exhausted(self):
        db = _make_db(rowcount=3)
        count = await mark_empty_bars(db, "uuid-abc", "QUOTA_EXHAUSTED")
        assert count == 3

    @pytest.mark.asyncio
    async def test_zero_when_no_stale_bars(self):
        db = _make_db(rowcount=0)
        count = await mark_empty_bars(db, "uuid-abc", "UNAVAILABLE")
        assert count == 0

    @pytest.mark.asyncio
    async def test_invalid_status_raises_value_error(self):
        db = _make_db()
        with pytest.raises(ValueError, match="tidak valid"):
            await mark_empty_bars(db, "uuid-abc", "FRESH")

    @pytest.mark.asyncio
    async def test_calls_execute_once(self):
        db = _make_db(rowcount=2)
        await mark_empty_bars(db, "uuid-abc", "UNAVAILABLE")
        db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# CoverageStatusResponse schema
# ---------------------------------------------------------------------------

class TestCoverageStatusResponseSchema:
    def test_schema_valid(self):
        from app.api.schemas import CoverageStatusResponse
        r = CoverageStatusResponse(
            fresh=1000, stale=50, unavailable=12, quota_exhausted=3,
            other=5, total=1070, stale_pct=4.7,
            unavailable_instruments=8, quota_instruments=2,
        )
        assert r.total == 1070
        assert r.stale_pct == 4.7

    def test_zero_state(self):
        from app.api.schemas import CoverageStatusResponse
        r = CoverageStatusResponse(
            fresh=0, stale=0, unavailable=0, quota_exhausted=0,
            other=0, total=0, stale_pct=0.0,
            unavailable_instruments=0, quota_instruments=0,
        )
        assert r.total == 0
