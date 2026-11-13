"""
Unit tests FREE-14 — Provider fallback chain.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.provider_fallback import FallbackIngestResult, ingest_with_fallback


# ---------------------------------------------------------------------------
# FallbackIngestResult dataclass
# ---------------------------------------------------------------------------

class TestFallbackIngestResult:
    def test_defaults(self):
        ohlcv = MagicMock()
        r = FallbackIngestResult(ohlcv=ohlcv, provider_used="yfinance")
        assert r.providers_tried == []
        assert r.fallback_used is False

    def test_with_fallback(self):
        ohlcv = MagicMock()
        r = FallbackIngestResult(
            ohlcv=ohlcv,
            provider_used="openbb",
            providers_tried=["yfinance", "openbb"],
            fallback_used=True,
        )
        assert r.fallback_used is True
        assert len(r.providers_tried) == 2


# ---------------------------------------------------------------------------
# ingest_with_fallback
# ---------------------------------------------------------------------------

def _make_instrument(symbol: str = "IDX:BBCA", exchange: str = "IDX") -> MagicMock:
    instr = MagicMock()
    instr.canonical_symbol = symbol
    instr.exchange = exchange
    return instr


def _make_ohlcv_result(inserted: int = 5, skipped: int = 0) -> MagicMock:
    r = MagicMock()
    r.inserted = inserted
    r.skipped = skipped
    r.validation_errors = []
    return r


def _make_provider(name: str) -> MagicMock:
    p = MagicMock()
    p.name = name
    return p


class TestIngestWithFallback:
    @pytest.mark.asyncio
    async def test_primary_succeeds_no_fallback(self):
        db = MagicMock()
        instr = _make_instrument()
        ohlcv_ok = _make_ohlcv_result(inserted=10)

        provider_a = _make_provider("yfinance")

        with patch("app.ingestion.provider_fallback.get_provider_registry") as mock_reg:
            mock_reg.return_value.get_ordered.return_value = [provider_a]
            with patch("app.ingestion.provider_fallback.ingest_ohlcv", new=AsyncMock(return_value=ohlcv_ok)):
                result = await ingest_with_fallback(db, instr, "IDX", date(2025, 1, 1), date(2026, 1, 1))

        assert result is not None
        assert result.ohlcv.inserted == 10
        assert result.fallback_used is False
        assert result.provider_used == "yfinance"

    @pytest.mark.asyncio
    async def test_primary_empty_falls_back_to_secondary(self):
        db = MagicMock()
        instr = _make_instrument()
        ohlcv_empty = _make_ohlcv_result(inserted=0, skipped=0)
        ohlcv_ok = _make_ohlcv_result(inserted=5)

        provider_a = _make_provider("yfinance")
        provider_b = _make_provider("openbb")

        call_count = 0

        async def mock_ingest(db, instr, provider, start, end, force=False):
            nonlocal call_count
            call_count += 1
            if provider is provider_a:
                return ohlcv_empty
            return ohlcv_ok

        with patch("app.ingestion.provider_fallback.get_provider_registry") as mock_reg:
            mock_reg.return_value.get_ordered.return_value = [provider_a, provider_b]
            with patch("app.ingestion.provider_fallback.ingest_ohlcv", side_effect=mock_ingest):
                result = await ingest_with_fallback(db, instr, "IDX", date(2025, 1, 1), date(2026, 1, 1))

        assert result is not None
        assert result.fallback_used is True
        assert result.provider_used == "openbb"
        assert "yfinance" in result.providers_tried
        assert "openbb" in result.providers_tried

    @pytest.mark.asyncio
    async def test_all_providers_empty_returns_none(self):
        db = MagicMock()
        instr = _make_instrument()
        ohlcv_empty = _make_ohlcv_result(inserted=0, skipped=0)

        provider_a = _make_provider("yfinance")
        provider_b = _make_provider("openbb")

        with patch("app.ingestion.provider_fallback.get_provider_registry") as mock_reg:
            mock_reg.return_value.get_ordered.return_value = [provider_a, provider_b]
            with patch("app.ingestion.provider_fallback.ingest_ohlcv", new=AsyncMock(return_value=ohlcv_empty)):
                result = await ingest_with_fallback(db, instr, "IDX", date(2025, 1, 1), date(2026, 1, 1))

        assert result is None

    @pytest.mark.asyncio
    async def test_provider_exception_tries_next(self):
        db = MagicMock()
        instr = _make_instrument()
        ohlcv_ok = _make_ohlcv_result(inserted=3)

        provider_a = _make_provider("yfinance")
        provider_b = _make_provider("openbb")

        async def mock_ingest(db, instr, provider, start, end, force=False):
            if provider is provider_a:
                raise ConnectionError("yfinance timeout")
            return ohlcv_ok

        with patch("app.ingestion.provider_fallback.get_provider_registry") as mock_reg:
            mock_reg.return_value.get_ordered.return_value = [provider_a, provider_b]
            with patch("app.ingestion.provider_fallback.ingest_ohlcv", side_effect=mock_ingest):
                result = await ingest_with_fallback(db, instr, "IDX", date(2025, 1, 1), date(2026, 1, 1))

        assert result is not None
        assert result.provider_used == "openbb"
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_no_providers_returns_none(self):
        db = MagicMock()
        instr = _make_instrument()

        with patch("app.ingestion.provider_fallback.get_provider_registry") as mock_reg:
            mock_reg.return_value.get_ordered.return_value = []
            result = await ingest_with_fallback(db, instr, "IDX", date(2025, 1, 1), date(2026, 1, 1))

        assert result is None

    @pytest.mark.asyncio
    async def test_mock_provider_skipped_by_default(self):
        db = MagicMock()
        instr = _make_instrument()
        ohlcv_ok = _make_ohlcv_result(inserted=5)

        provider_mock = _make_provider("mock_provider")  # name contains "mock"

        with patch("app.ingestion.provider_fallback.get_provider_registry") as mock_reg:
            mock_reg.return_value.get_ordered.return_value = [provider_mock]
            with patch("app.ingestion.provider_fallback.ingest_ohlcv", new=AsyncMock(return_value=ohlcv_ok)):
                result = await ingest_with_fallback(db, instr, "IDX", date(2025, 1, 1), date(2026, 1, 1))

        # Mock provider di-skip → result None meski mock bisa serve
        assert result is None

    @pytest.mark.asyncio
    async def test_skipped_bars_count_as_success(self):
        """skipped > 0 berarti data sudah ada (idempoten) — dihitung sukses."""
        db = MagicMock()
        instr = _make_instrument()
        ohlcv_skipped = _make_ohlcv_result(inserted=0, skipped=10)

        provider_a = _make_provider("yfinance")

        with patch("app.ingestion.provider_fallback.get_provider_registry") as mock_reg:
            mock_reg.return_value.get_ordered.return_value = [provider_a]
            with patch("app.ingestion.provider_fallback.ingest_ohlcv", new=AsyncMock(return_value=ohlcv_skipped)):
                result = await ingest_with_fallback(db, instr, "IDX", date(2025, 1, 1), date(2026, 1, 1))

        assert result is not None
        assert result.ohlcv.skipped == 10


# ---------------------------------------------------------------------------
# registry.get_ordered
# ---------------------------------------------------------------------------

class TestRegistryGetOrdered:
    def test_get_ordered_returns_list(self):
        from app.providers.registry import get_provider_registry
        registry = get_provider_registry()
        for market in ("IDX", "US"):
            providers = registry.get_ordered(market)
            assert isinstance(providers, list)

    def test_get_ordered_unknown_market_returns_empty(self):
        from app.providers.registry import get_provider_registry
        registry = get_provider_registry()
        providers = registry.get_ordered("NONEXISTENT")
        assert providers == []

    def test_get_ordered_is_copy(self):
        """Mutasi list yang dikembalikan tidak mempengaruhi registry."""
        from app.providers.registry import get_provider_registry
        registry = get_provider_registry()
        ordered = registry.get_ordered("IDX")
        original_len = len(ordered)
        ordered.clear()
        assert len(registry.get_ordered("IDX")) == original_len
