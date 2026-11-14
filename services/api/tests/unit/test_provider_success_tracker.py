"""
Unit tests FREE-26 — Provider success rate tracker.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.providers.success_tracker import ProviderSuccessStats, ProviderSuccessTracker


# ---------------------------------------------------------------------------
# ProviderSuccessStats — computed properties
# ---------------------------------------------------------------------------

class TestProviderSuccessStats:
    def test_total_calls_zero(self):
        s = ProviderSuccessStats(provider_name="yfinance", date_str="2026-11-14")
        assert s.total_calls == 0

    def test_total_calls_sum(self):
        s = ProviderSuccessStats(provider_name="yfinance", date_str="2026-11-14",
                                 calls_succeeded=7, calls_failed=3)
        assert s.total_calls == 10

    def test_success_rate_zero_when_no_calls(self):
        s = ProviderSuccessStats(provider_name="yfinance", date_str="2026-11-14")
        assert s.success_rate == 0.0

    def test_success_rate_100(self):
        s = ProviderSuccessStats(provider_name="yfinance", date_str="2026-11-14",
                                 calls_succeeded=5, calls_failed=0)
        assert s.success_rate == 100.0

    def test_success_rate_partial(self):
        s = ProviderSuccessStats(provider_name="yfinance", date_str="2026-11-14",
                                 calls_succeeded=3, calls_failed=1)
        assert s.success_rate == 75.0

    def test_success_rate_rounded(self):
        s = ProviderSuccessStats(provider_name="yfinance", date_str="2026-11-14",
                                 calls_succeeded=1, calls_failed=2)
        # 1/3 * 100 = 33.333... → rounded to 33.3
        assert s.success_rate == 33.3


# ---------------------------------------------------------------------------
# ProviderSuccessTracker — record_success / record_failure
# ---------------------------------------------------------------------------

class TestProviderSuccessTracker:
    def _tracker(self) -> ProviderSuccessTracker:
        t = ProviderSuccessTracker()
        return t

    def test_record_success_increments_succeeded(self):
        t = self._tracker()
        t.record_success("yfinance", bars=10)
        t.record_success("yfinance", bars=5)
        s = t.get_stats("yfinance")
        assert s is not None
        assert s.calls_succeeded == 2
        assert s.calls_failed == 0
        assert s.bars_fetched == 15

    def test_record_failure_increments_failed(self):
        t = self._tracker()
        t.record_failure("yfinance", error="Connection timeout")
        t.record_failure("yfinance", error="Rate limited")
        s = t.get_stats("yfinance")
        assert s is not None
        assert s.calls_failed == 2
        assert s.calls_succeeded == 0
        assert s.last_error == "Rate limited"

    def test_mixed_calls(self):
        t = self._tracker()
        t.record_success("yfinance", bars=20)
        t.record_failure("yfinance", error="err")
        t.record_success("yfinance", bars=10)
        s = t.get_stats("yfinance")
        assert s.calls_succeeded == 2
        assert s.calls_failed == 1
        assert s.total_calls == 3
        assert s.bars_fetched == 30

    def test_multiple_providers_isolated(self):
        t = self._tracker()
        t.record_success("yfinance", bars=5)
        t.record_failure("sectors", error="auth")
        yf = t.get_stats("yfinance")
        sec = t.get_stats("sectors")
        assert yf.calls_succeeded == 1
        assert sec.calls_failed == 1
        assert yf.calls_failed == 0
        assert sec.calls_succeeded == 0

    def test_get_stats_returns_none_for_unknown(self):
        t = self._tracker()
        assert t.get_stats("nonexistent") is None

    def test_all_stats_sorted_by_total_desc(self):
        t = self._tracker()
        t.record_success("slow_provider")
        t.record_success("busy_provider")
        t.record_success("busy_provider")
        t.record_success("busy_provider")
        all_s = t.all_stats()
        assert all_s[0].provider_name == "busy_provider"
        assert all_s[1].provider_name == "slow_provider"

    def test_reset_all_clears_stats(self):
        t = self._tracker()
        t.record_success("yfinance", bars=10)
        t.reset_all()
        assert t.get_stats("yfinance") is None
        assert t.all_stats() == []

    def test_last_success_at_set(self):
        t = self._tracker()
        before = datetime.now(tz=timezone.utc)
        t.record_success("yfinance", bars=1)
        after = datetime.now(tz=timezone.utc)
        s = t.get_stats("yfinance")
        assert s.last_success_at is not None
        assert before <= s.last_success_at <= after

    def test_last_failure_at_set(self):
        t = self._tracker()
        t.record_failure("yfinance", error="boom")
        s = t.get_stats("yfinance")
        assert s.last_failure_at is not None

    def test_error_truncated_at_256(self):
        t = self._tracker()
        long_error = "x" * 500
        t.record_failure("yfinance", error=long_error)
        s = t.get_stats("yfinance")
        assert len(s.last_error) == 256

    def test_daily_reset_on_new_day(self):
        t = self._tracker()
        t.record_success("yfinance", bars=5)
        from datetime import date
        future = date(2030, 1, 1)
        with patch("app.providers.success_tracker.date") as mock_date:
            mock_date.today.return_value = future
            t.record_success("yfinance", bars=3)  # triggers reset then records
            s = t.get_stats("yfinance")  # check inside patch so date is still future
        # After reset, only the post-reset call remains
        assert s is not None
        assert s.calls_succeeded == 1
        assert s.bars_fetched == 3


# ---------------------------------------------------------------------------
# Integration: get_success_tracker singleton
# ---------------------------------------------------------------------------

class TestGetSuccessTrackerSingleton:
    def test_singleton(self):
        from app.providers.success_tracker import get_success_tracker
        a = get_success_tracker()
        b = get_success_tracker()
        assert a is b


# ---------------------------------------------------------------------------
# Endpoint AST check
# ---------------------------------------------------------------------------

class TestEndpointIntegration:
    def test_provider_stats_endpoint_exists(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent / "app" / "api" / "routes" / "data_health.py"
        content = src.read_text()
        assert "/provider-stats" in content
        assert "ProviderSuccessResponse" in content
        assert "get_success_tracker" in content

    def test_provider_stats_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "ProviderSuccessRow" in content
        assert "ProviderSuccessResponse" in content
        assert "providerStats" in content
        assert "/data/provider-stats" in content

    def test_provider_stats_section_in_settings(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "settings" / "page.tsx"
        if not src.exists():
            pytest.skip("settings/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "ProviderStatsSection" in content
        assert "Provider Success Rate" in content
        assert "success_rate" in content
