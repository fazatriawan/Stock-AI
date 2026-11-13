"""
Unit tests FREE-01 ProviderCapability dan FREE-03 budget guard.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.providers.base import AccessStatus, LicenseStatus, ProviderCapability
from app.providers.mock_provider import MockProvider
from app.providers.yfinance_provider import YFinanceProvider
from app.providers.registry import ProviderRegistry


# ---------------------------------------------------------------------------
# FREE-01 — ProviderCapability
# ---------------------------------------------------------------------------

class TestProviderCapability:
    def test_mock_capability_fields(self):
        cap = MockProvider().capability()
        assert isinstance(cap, ProviderCapability)
        assert cap.license_status == LicenseStatus.FREE_PERSONAL
        assert cap.access_status == AccessStatus.ACTIVE
        assert cap.cost == "free"
        assert cap.supports_point_in_time is False
        assert "ohlcv" in cap.datasets

    def test_yfinance_capability_active_when_installed(self):
        cap = YFinanceProvider().capability()
        assert cap.license_status == LicenseStatus.FREE_PERSONAL
        assert cap.cost == "free"
        assert cap.access_status == AccessStatus.ACTIVE
        assert "ohlcv" in cap.datasets
        assert "fundamental" in cap.datasets

    def test_yfinance_capability_not_configured_when_missing(self):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "yfinance":
                raise ImportError("not installed")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            yf = YFinanceProvider()
            cap = yf.capability()
        assert cap.access_status == AccessStatus.NOT_CONFIGURED


# ---------------------------------------------------------------------------
# FREE-03 — Budget guard di ProviderRegistry
# ---------------------------------------------------------------------------

class TestBudgetGuard:
    def test_sectors_blocked_when_paid_disabled(self, caplog):
        """Sectors tidak masuk registry jika paid_providers_enabled=False."""
        import logging
        with patch("app.providers.registry.get_settings") as mock_settings:
            mock_settings.return_value.sectors_enabled = True
            mock_settings.return_value.sectors_api_key = "dummy_key"
            mock_settings.return_value.paid_providers_enabled = False
            mock_settings.return_value.yfinance_enabled = False
            mock_settings.return_value.openbb_enabled = False

            registry = ProviderRegistry()

        assert "sectors" not in registry._provider_by_name
        # provider utama IDX harus fallback ke mock
        primary = registry.get_primary("IDX")
        assert primary is registry._mock

    def test_sectors_active_when_paid_enabled(self):
        """Sectors masuk registry jika paid_providers_enabled=True."""
        with patch("app.providers.registry.get_settings") as mock_settings, \
             patch("app.providers.registry.SectorsProvider") as mock_sectors_cls:
            mock_settings.return_value.sectors_enabled = True
            mock_settings.return_value.sectors_api_key = "real_key"
            mock_settings.return_value.paid_providers_enabled = True
            mock_settings.return_value.yfinance_enabled = False
            mock_settings.return_value.openbb_enabled = False

            mock_sectors_cls.return_value.name = "sectors"
            registry = ProviderRegistry()

        assert "sectors" in registry._provider_by_name

    def test_free_providers_always_active(self):
        """yfinance tetap aktif tanpa paid_providers_enabled."""
        with patch("app.providers.registry.get_settings") as mock_settings:
            mock_settings.return_value.sectors_enabled = False
            mock_settings.return_value.sectors_api_key = ""
            mock_settings.return_value.paid_providers_enabled = False
            mock_settings.return_value.yfinance_enabled = True
            mock_settings.return_value.openbb_enabled = False

            registry = ProviderRegistry()

        assert "yfinance" in registry._provider_by_name
