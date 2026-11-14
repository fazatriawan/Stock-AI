"""
Unit tests FREE-19 — Per-instrument on-demand data refresh endpoint.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.provider_fallback import FallbackIngestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_result(inserted: int = 10, skipped: int = 0) -> MagicMock:
    r = MagicMock()
    r.inserted = inserted
    r.skipped = skipped
    r.validation_errors = []
    return r


def _make_fallback_result(
    inserted: int = 10,
    provider: str = "yfinance",
    fallback_used: bool = False,
    providers_tried: list[str] | None = None,
) -> FallbackIngestResult:
    ohlcv = _make_ohlcv_result(inserted=inserted)
    return FallbackIngestResult(
        ohlcv=ohlcv,
        provider_used=provider,
        providers_tried=providers_tried or [provider],
        fallback_used=fallback_used,
    )


def _make_gap_detect_result(gap_pct: float = 5.0, instrument_id: str = "uuid-bbca") -> MagicMock:
    report = MagicMock()
    report.instrument_id = instrument_id
    report.gap_pct = gap_pct

    result = MagicMock()
    result.reports = [report]
    return result


# ---------------------------------------------------------------------------
# StockRefreshResult schema
# ---------------------------------------------------------------------------

class TestStockRefreshResultSchema:
    def test_ok_response_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "StockRefreshResult" in content
        assert "refreshData" in content
        assert "provider_used" in content
        assert "fallback_used" in content
        assert "gap_pct_before" in content

    def test_refresh_button_in_explorer(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "explorer" / "page.tsx"
        if not src.exists():
            pytest.skip("explorer/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "handleRefresh" in content
        assert "refreshData" in content
        assert "Refresh Data" in content


# ---------------------------------------------------------------------------
# refresh_data_with_fallback endpoint logic
# (test via direct function call, not HTTP client)
# ---------------------------------------------------------------------------

class TestRefreshDataLogic:
    @pytest.mark.asyncio
    async def test_returns_ok_when_provider_succeeds(self):
        """Endpoint mengembalikan status ok + bars_added saat provider berhasil."""
        from app.api.routes.stocks import refresh_data_with_fallback

        db = MagicMock()
        db.commit = AsyncMock()

        fb_result = _make_fallback_result(inserted=15, provider="yfinance")
        gap_detect = _make_gap_detect_result(gap_pct=5.0)

        with patch("app.api.routes.stocks._get_instrument_or_404") as mock_get:
            instr = MagicMock()
            instr.canonical_symbol = "IDX:BBCA"
            instr.exchange = "IDX"
            instr.id = "uuid-bbca"
            mock_get.return_value = instr

            with patch("app.api.routes.stocks.ingest_with_fallback", new=AsyncMock(return_value=fb_result)):
                with patch("app.api.routes.stocks.detect_data_gaps", new=AsyncMock(return_value=gap_detect)):
                    response = await refresh_data_with_fallback("IDX:BBCA", days_back=365, db=db)

        assert response["status"] == "ok"
        assert response["bars_added"] == 15
        assert response["provider_used"] == "yfinance"
        assert response["fallback_used"] is False

    @pytest.mark.asyncio
    async def test_returns_no_data_when_all_providers_fail(self):
        """Semua provider gagal → status no_data."""
        from app.api.routes.stocks import refresh_data_with_fallback

        db = MagicMock()
        db.commit = AsyncMock()

        gap_detect = _make_gap_detect_result()

        with patch("app.api.routes.stocks._get_instrument_or_404") as mock_get:
            instr = MagicMock()
            instr.canonical_symbol = "IDX:BBCA"
            instr.exchange = "IDX"
            instr.id = "uuid-bbca"
            mock_get.return_value = instr

            with patch("app.api.routes.stocks.ingest_with_fallback", new=AsyncMock(return_value=None)):
                with patch("app.api.routes.stocks.detect_data_gaps", new=AsyncMock(return_value=gap_detect)):
                    response = await refresh_data_with_fallback("IDX:BBCA", days_back=365, db=db)

        assert response["status"] == "no_data"
        assert response["bars_added"] == 0
        assert response["provider_used"] is None

    @pytest.mark.asyncio
    async def test_fallback_used_flag_propagated(self):
        """fallback_used=True dari FallbackIngestResult diteruskan ke response."""
        from app.api.routes.stocks import refresh_data_with_fallback

        db = MagicMock()
        db.commit = AsyncMock()

        fb_result = _make_fallback_result(inserted=5, provider="openbb", fallback_used=True, providers_tried=["yfinance", "openbb"])
        gap_detect = _make_gap_detect_result()

        with patch("app.api.routes.stocks._get_instrument_or_404") as mock_get:
            instr = MagicMock()
            instr.canonical_symbol = "US:AAPL"
            instr.exchange = "NASDAQ"
            instr.id = "uuid-aapl"
            mock_get.return_value = instr

            with patch("app.api.routes.stocks.ingest_with_fallback", new=AsyncMock(return_value=fb_result)):
                with patch("app.api.routes.stocks.detect_data_gaps", new=AsyncMock(return_value=gap_detect)):
                    response = await refresh_data_with_fallback("AAPL", days_back=365, db=db)

        assert response["fallback_used"] is True
        assert response["provider_used"] == "openbb"
        assert response["providers_tried"] == ["yfinance", "openbb"]

    @pytest.mark.asyncio
    async def test_us_market_routing(self):
        """Instrumen US dikirim ke market='US' di ingest_with_fallback."""
        from app.api.routes.stocks import refresh_data_with_fallback

        db = MagicMock()
        db.commit = AsyncMock()

        fb_result = _make_fallback_result()
        gap_detect = _make_gap_detect_result()
        mock_ingest = AsyncMock(return_value=fb_result)

        with patch("app.api.routes.stocks._get_instrument_or_404") as mock_get:
            instr = MagicMock()
            instr.canonical_symbol = "MSFT"
            instr.exchange = "NASDAQ"
            instr.id = "uuid-msft"
            mock_get.return_value = instr

            with patch("app.api.routes.stocks.ingest_with_fallback", mock_ingest):
                with patch("app.api.routes.stocks.detect_data_gaps", new=AsyncMock(return_value=gap_detect)):
                    await refresh_data_with_fallback("MSFT", days_back=365, db=db)

        call_args = mock_ingest.call_args
        market = call_args[0][2] if len(call_args[0]) > 2 else call_args.kwargs.get("market")
        assert market == "US"

    @pytest.mark.asyncio
    async def test_idx_market_routing(self):
        """Instrumen IDX dikirim ke market='IDX'."""
        from app.api.routes.stocks import refresh_data_with_fallback

        db = MagicMock()
        db.commit = AsyncMock()

        fb_result = _make_fallback_result()
        gap_detect = _make_gap_detect_result()
        mock_ingest = AsyncMock(return_value=fb_result)

        with patch("app.api.routes.stocks._get_instrument_or_404") as mock_get:
            instr = MagicMock()
            instr.canonical_symbol = "IDX:BBCA"
            instr.exchange = "IDX"
            instr.id = "uuid-bbca"
            mock_get.return_value = instr

            with patch("app.api.routes.stocks.ingest_with_fallback", mock_ingest):
                with patch("app.api.routes.stocks.detect_data_gaps", new=AsyncMock(return_value=gap_detect)):
                    await refresh_data_with_fallback("IDX:BBCA", days_back=365, db=db)

        call_args = mock_ingest.call_args
        market = call_args[0][2] if len(call_args[0]) > 2 else call_args.kwargs.get("market")
        assert market == "IDX"

    @pytest.mark.asyncio
    async def test_force_true_passed(self):
        """force=True selalu dikirim ke ingest_with_fallback."""
        from app.api.routes.stocks import refresh_data_with_fallback

        db = MagicMock()
        db.commit = AsyncMock()

        fb_result = _make_fallback_result()
        gap_detect = _make_gap_detect_result()
        mock_ingest = AsyncMock(return_value=fb_result)

        with patch("app.api.routes.stocks._get_instrument_or_404") as mock_get:
            instr = MagicMock()
            instr.canonical_symbol = "IDX:BBCA"
            instr.exchange = "IDX"
            instr.id = "uuid-bbca"
            mock_get.return_value = instr

            with patch("app.api.routes.stocks.ingest_with_fallback", mock_ingest):
                with patch("app.api.routes.stocks.detect_data_gaps", new=AsyncMock(return_value=gap_detect)):
                    await refresh_data_with_fallback("IDX:BBCA", days_back=365, db=db)

        call_kwargs = mock_ingest.call_args.kwargs
        assert call_kwargs.get("force") is True or mock_ingest.call_args[1].get("force") is True
