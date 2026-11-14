"""
Unit tests FREE-22 — Stale instruments list + nightly gap-heal job.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Scheduler: _run_gap_heal
# ---------------------------------------------------------------------------

class TestRunGapHeal:
    @pytest.mark.asyncio
    async def test_records_ok_on_success(self):
        from app.scheduling.scheduler import _run_gap_heal

        heal_result = MagicMock()
        heal_result.instruments_found = 3
        heal_result.instruments_healed = 2
        heal_result.bars_added = 50
        heal_result.errors = []

        mock_tracker = MagicMock()
        mock_record = MagicMock()
        mock_tracker.start_run.return_value = mock_record

        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=db_mock)
        ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("app.scheduling.scheduler._tracker", return_value=mock_tracker):
            with patch("app.db.session.AsyncSessionLocal", return_value=ctx):
                with patch("app.analytics.gap_healer.heal_data_gaps", new=AsyncMock(return_value=heal_result)):
                    await _run_gap_heal()

        mock_tracker.finish_run.assert_called_once()
        call_kwargs = mock_tracker.finish_run.call_args
        assert call_kwargs[1].get("status") == "ok" or (call_kwargs[0] and call_kwargs[0][1] == "ok")

    @pytest.mark.asyncio
    async def test_records_error_on_exception(self):
        from app.scheduling.scheduler import _run_gap_heal

        mock_tracker = MagicMock()
        mock_record = MagicMock()
        mock_tracker.start_run.return_value = mock_record

        with patch("app.scheduling.scheduler._tracker", return_value=mock_tracker):
            with patch("app.analytics.gap_healer.heal_data_gaps", new=AsyncMock(side_effect=RuntimeError("db_down"))):
                with patch("app.db.session.AsyncSessionLocal") as mock_session:
                    ctx = MagicMock()
                    ctx.__aenter__ = AsyncMock(return_value=MagicMock())
                    ctx.__aexit__ = AsyncMock(return_value=None)
                    mock_session.return_value = ctx
                    await _run_gap_heal()

        mock_tracker.finish_run.assert_called_once()
        call_kwargs = mock_tracker.finish_run.call_args
        assert call_kwargs[1].get("status") == "error" or (call_kwargs[0] and call_kwargs[0][1] == "error")


# ---------------------------------------------------------------------------
# Scheduler: gap_heal job registered
# ---------------------------------------------------------------------------

class TestGapHealJobRegistered:
    def test_gap_heal_in_all_jobs_list(self):
        import inspect
        import app.scheduling.scheduler as sched_module
        src = inspect.getsource(sched_module.create_scheduler)
        assert "gap_heal" in src

    def test_gap_heal_cron_hour_3(self):
        import inspect
        import app.scheduling.scheduler as sched_module
        src = inspect.getsource(sched_module.create_scheduler)
        # Confirm 03:30 WIB schedule is present
        assert "hour=3" in src or "hour=3, minute=30" in src


# ---------------------------------------------------------------------------
# StaleInstrumentsResponse schema
# ---------------------------------------------------------------------------

class TestStaleInstrumentSchema:
    def test_stale_instrument_row_fields(self):
        from app.api.schemas import StaleInstrumentRow
        row = StaleInstrumentRow(
            instrument_id="uuid-bbca",
            canonical_symbol="IDX:BBCA",
            exchange="IDX",
            stale_count=10,
            fresh_count=240,
            total_count=250,
            stale_pct=4.0,
            last_fresh_date="2026-11-10",
        )
        assert row.stale_pct == 4.0
        assert row.last_fresh_date == "2026-11-10"

    def test_stale_instruments_response_fields(self):
        from datetime import datetime, timezone
        from app.api.schemas import StaleInstrumentRow, StaleInstrumentsResponse
        row = StaleInstrumentRow(
            instrument_id="x",
            canonical_symbol="AAPL",
            exchange="NASDAQ",
            stale_count=5,
            fresh_count=100,
            total_count=105,
            stale_pct=4.8,
            last_fresh_date=None,
        )
        resp = StaleInstrumentsResponse(
            instruments=[row],
            total_instruments=1,
            total_stale_bars=5,
            ran_at=datetime.now(tz=timezone.utc),
        )
        assert resp.total_instruments == 1
        assert resp.total_stale_bars == 5


# ---------------------------------------------------------------------------
# AST check — api.ts + settings page
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_stale_instruments_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "StaleInstrumentRow" in content
        assert "StaleInstrumentsStatus" in content
        assert "staleInstruments" in content

    def test_stale_instruments_section_in_settings(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "settings" / "page.tsx"
        if not src.exists():
            pytest.skip("settings/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "StaleInstrumentsSection" in content
        assert "staleInstruments" in content
