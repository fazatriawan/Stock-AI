"""
Unit tests FREE-16 — Admin quota tracker reset endpoint + schema checks.
"""
from __future__ import annotations

import pytest

from app.providers.quota_tracker import ProviderQuotaTracker
from app.api.schemas import ProviderQuotaRow, ProviderQuotaResponse


# ---------------------------------------------------------------------------
# ProviderQuotaRow / ProviderQuotaResponse schema
# ---------------------------------------------------------------------------

class TestProviderQuotaSchemas:
    def test_quota_row_basic(self):
        row = ProviderQuotaRow(
            provider_name="yfinance",
            calls_today=42,
            quota_per_day=1000,
            quota_exhausted=False,
            date_str="2026-11-13",
        )
        assert row.calls_today == 42
        assert row.quota_per_day == 1000
        assert row.quota_exhausted is False

    def test_quota_row_no_quota(self):
        row = ProviderQuotaRow(
            provider_name="openbb",
            calls_today=5,
            quota_per_day=None,
            quota_exhausted=False,
            date_str="2026-11-13",
        )
        assert row.quota_per_day is None

    def test_quota_row_exhausted(self):
        row = ProviderQuotaRow(
            provider_name="yfinance",
            calls_today=1000,
            quota_per_day=1000,
            quota_exhausted=True,
            date_str="2026-11-13",
        )
        assert row.quota_exhausted is True

    def test_provider_quota_response(self):
        from datetime import datetime, timezone
        rows = [
            ProviderQuotaRow(
                provider_name="yfinance", calls_today=50, quota_per_day=1000,
                quota_exhausted=False, date_str="2026-11-13",
            ),
            ProviderQuotaRow(
                provider_name="openbb", calls_today=10, quota_per_day=None,
                quota_exhausted=False, date_str="2026-11-13",
            ),
        ]
        resp = ProviderQuotaResponse(
            providers=rows,
            total_calls_today=60,
            as_of=datetime.now(tz=timezone.utc),
        )
        assert resp.total_calls_today == 60
        assert len(resp.providers) == 2

    def test_provider_quota_response_empty(self):
        from datetime import datetime, timezone
        resp = ProviderQuotaResponse(
            providers=[],
            total_calls_today=0,
            as_of=datetime.now(tz=timezone.utc),
        )
        assert resp.providers == []


# ---------------------------------------------------------------------------
# Admin reset endpoint (via tracker directly)
# ---------------------------------------------------------------------------

class TestQuotaTrackerReset:
    def test_reset_clears_all_counts(self):
        tracker = ProviderQuotaTracker()
        tracker.record_call("yfinance")
        tracker.record_call("openbb")
        assert tracker.get_calls_today("yfinance") == 1
        assert tracker.get_calls_today("openbb") == 1

        tracker.reset_all()

        assert tracker.get_calls_today("yfinance") == 0
        assert tracker.get_calls_today("openbb") == 0

    def test_reset_all_stats_empty_after_reset(self):
        tracker = ProviderQuotaTracker()
        tracker.record_call("yfinance")
        tracker.reset_all()
        assert tracker.all_stats() == []

    def test_reset_does_not_affect_other_tracker(self):
        """Dua tracker instance independen satu sama lain."""
        t1 = ProviderQuotaTracker()
        t2 = ProviderQuotaTracker()
        t1.record_call("yfinance")
        t2.record_call("openbb")
        t1.reset_all()
        assert t2.get_calls_today("openbb") == 1


# ---------------------------------------------------------------------------
# AST check: api.ts contains ProviderQuotaStatus + resetQuotaTracker
# ---------------------------------------------------------------------------

class TestFrontendTypes:
    def test_provider_quota_status_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "ProviderQuotaStatus" in content, "ProviderQuotaStatus interface tidak ada di api.ts"
        assert "ProviderQuotaRow" in content, "ProviderQuotaRow interface tidak ada di api.ts"
        assert "providerQuota" in content, "api.data.providerQuota tidak ada di api.ts"
        assert "resetQuotaTracker" in content, "api.admin.resetQuotaTracker tidak ada di api.ts"

    def test_provider_quota_section_in_settings(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "settings" / "page.tsx"
        if not src.exists():
            pytest.skip("settings/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "ProviderQuotaSection" in content, "ProviderQuotaSection tidak ada di settings/page.tsx"
        assert "resetQuotaTracker" in content, "resetQuotaTracker tidak dipanggil di settings/page.tsx"
