"""
Unit tests FREE-15 — Per-provider daily call counter.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.providers.base import ProviderCapability, LicenseStatus, AccessStatus
from app.providers.quota_tracker import ProviderQuotaTracker, get_quota_tracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker() -> ProviderQuotaTracker:
    """Buat tracker baru (bukan singleton) untuk isolasi test."""
    return ProviderQuotaTracker()


def _make_cap(quota_per_day: int | None) -> ProviderCapability:
    return ProviderCapability(
        license_status=LicenseStatus.FREE_PERSONAL,
        access_status=AccessStatus.ACTIVE,
        cost="free",
        granularity="daily",
        freshness_policy="EOD",
        supports_point_in_time=False,
        quota_per_day=quota_per_day,
    )


# ---------------------------------------------------------------------------
# ProviderQuotaTracker — basic counter
# ---------------------------------------------------------------------------

class TestProviderQuotaTracker:
    def test_initial_calls_zero(self):
        t = _make_tracker()
        assert t.get_calls_today("yfinance") == 0

    def test_record_call_increments(self):
        t = _make_tracker()
        t.record_call("yfinance")
        t.record_call("yfinance")
        assert t.get_calls_today("yfinance") == 2

    def test_different_providers_independent(self):
        t = _make_tracker()
        t.record_call("yfinance")
        t.record_call("openbb")
        t.record_call("openbb")
        assert t.get_calls_today("yfinance") == 1
        assert t.get_calls_today("openbb") == 2

    def test_record_call_returns_count(self):
        t = _make_tracker()
        assert t.record_call("yfinance") == 1
        assert t.record_call("yfinance") == 2

    def test_reset_provider(self):
        t = _make_tracker()
        t.record_call("yfinance")
        t.record_call("yfinance")
        t.reset_provider("yfinance")
        assert t.get_calls_today("yfinance") == 0

    def test_reset_all(self):
        t = _make_tracker()
        t.record_call("yfinance")
        t.record_call("openbb")
        t.reset_all()
        assert t.get_calls_today("yfinance") == 0
        assert t.get_calls_today("openbb") == 0

    def test_all_stats_empty(self):
        t = _make_tracker()
        assert t.all_stats() == []

    def test_all_stats_lists_providers(self):
        t = _make_tracker()
        t.record_call("yfinance")
        t.record_call("openbb")
        stats = t.all_stats()
        names = {s.provider_name for s in stats}
        assert "yfinance" in names
        assert "openbb" in names

    def test_daily_reset_on_date_change(self):
        """Counter reset otomatis saat tanggal berubah."""
        t = _make_tracker()
        t.record_call("yfinance")
        assert t.get_calls_today("yfinance") == 1

        # Simulasi tanggal berubah dengan mock date.today()
        with patch("app.providers.quota_tracker.date") as mock_date:
            mock_date.today.return_value = date(2099, 1, 1)
            assert t.get_calls_today("yfinance") == 0  # reset karena hari baru


# ---------------------------------------------------------------------------
# is_quota_exhausted
# ---------------------------------------------------------------------------

class TestIsQuotaExhausted:
    def test_no_quota_never_exhausted(self):
        t = _make_tracker()
        for _ in range(1000):
            t.record_call("yfinance")
        cap = _make_cap(quota_per_day=None)
        assert t.is_quota_exhausted("yfinance", cap) is False

    def test_none_capability_never_exhausted(self):
        t = _make_tracker()
        for _ in range(1000):
            t.record_call("yfinance")
        assert t.is_quota_exhausted("yfinance", None) is False

    def test_below_quota_not_exhausted(self):
        t = _make_tracker()
        cap = _make_cap(quota_per_day=100)
        for _ in range(99):
            t.record_call("yfinance")
        assert t.is_quota_exhausted("yfinance", cap) is False

    def test_at_quota_exhausted(self):
        t = _make_tracker()
        cap = _make_cap(quota_per_day=5)
        for _ in range(5):
            t.record_call("yfinance")
        assert t.is_quota_exhausted("yfinance", cap) is True

    def test_over_quota_exhausted(self):
        t = _make_tracker()
        cap = _make_cap(quota_per_day=5)
        for _ in range(10):
            t.record_call("yfinance")
        assert t.is_quota_exhausted("yfinance", cap) is True


# ---------------------------------------------------------------------------
# get_quota_tracker — singleton
# ---------------------------------------------------------------------------

class TestGetQuotaTracker:
    def test_returns_same_instance(self):
        t1 = get_quota_tracker()
        t2 = get_quota_tracker()
        assert t1 is t2

    def test_instance_is_tracker(self):
        assert isinstance(get_quota_tracker(), ProviderQuotaTracker)


# ---------------------------------------------------------------------------
# Integration: ingest_with_fallback skips quota-exhausted provider
# ---------------------------------------------------------------------------

class TestFallbackSkipsExhaustedProvider:
    @pytest.mark.asyncio
    async def test_exhausted_provider_skipped(self):
        """Provider di-skip jika quota sudah habis — fallback ke berikutnya."""
        from datetime import date
        from unittest.mock import AsyncMock
        from app.ingestion.provider_fallback import ingest_with_fallback

        db = MagicMock()
        instr = MagicMock()
        instr.canonical_symbol = "IDX:BBCA"
        instr.exchange = "IDX"

        ohlcv_ok = MagicMock()
        ohlcv_ok.inserted = 7
        ohlcv_ok.skipped = 0

        provider_a = MagicMock()
        provider_a.name = "quota_full_provider"
        cap_a = _make_cap(quota_per_day=0)   # quota 0 = selalu habis
        provider_a.capability.return_value = cap_a

        provider_b = MagicMock()
        provider_b.name = "fallback_provider"
        cap_b = _make_cap(quota_per_day=None)
        provider_b.capability.return_value = cap_b

        with patch("app.ingestion.provider_fallback.get_provider_registry") as mock_reg:
            mock_reg.return_value.get_ordered.return_value = [provider_a, provider_b]
            with patch("app.ingestion.provider_fallback.ingest_ohlcv", new=AsyncMock(return_value=ohlcv_ok)):
                with patch("app.ingestion.provider_fallback.get_quota_tracker") as mock_qt:
                    tracker = _make_tracker()
                    # Exhaust provider_a
                    for _ in range(10):
                        tracker.record_call("quota_full_provider")
                    mock_qt.return_value = tracker

                    result = await ingest_with_fallback(
                        db, instr, "IDX", date(2025, 1, 1), date(2026, 1, 1)
                    )

        # provider_a di-skip karena quota, provider_b berhasil
        # fallback_used=True karena provider_b ada di idx=1 dalam providers list
        assert result is not None
        assert result.provider_used == "fallback_provider"
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_all_exhausted_returns_none(self):
        """Semua provider quota habis → None."""
        from datetime import date
        from unittest.mock import AsyncMock
        from app.ingestion.provider_fallback import ingest_with_fallback

        db = MagicMock()
        instr = MagicMock()
        instr.canonical_symbol = "IDX:BBCA"
        instr.exchange = "IDX"

        provider_a = MagicMock()
        provider_a.name = "prov_a"
        cap_a = _make_cap(quota_per_day=0)
        provider_a.capability.return_value = cap_a

        with patch("app.ingestion.provider_fallback.get_provider_registry") as mock_reg:
            mock_reg.return_value.get_ordered.return_value = [provider_a]
            with patch("app.ingestion.provider_fallback.ingest_ohlcv", new=AsyncMock()):
                with patch("app.ingestion.provider_fallback.get_quota_tracker") as mock_qt:
                    tracker = _make_tracker()
                    mock_qt.return_value = tracker

                    result = await ingest_with_fallback(
                        db, instr, "IDX", date(2025, 1, 1), date(2026, 1, 1)
                    )

        assert result is None
