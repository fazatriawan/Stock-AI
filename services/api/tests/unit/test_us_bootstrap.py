"""
Unit tests FREE-10 — US stocks bootstrap.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.us_bootstrap import (
    US_HARDCODED_TICKERS,
    _ticker_to_instrument_info,
    run_us_bootstrap,
)


# ---------------------------------------------------------------------------
# Ticker list
# ---------------------------------------------------------------------------

class TestUSHardcodedTickers:
    def test_minimum_ticker_count(self):
        assert len(US_HARDCODED_TICKERS) >= 80

    def test_contains_mega_cap_tech(self):
        for ticker in ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"):
            assert ticker in US_HARDCODED_TICKERS, f"{ticker} tidak ada"

    def test_contains_etf(self):
        for etf in ("SPY", "QQQ", "GLD", "TLT"):
            assert etf in US_HARDCODED_TICKERS, f"{etf} tidak ada"

    def test_all_entries_have_name_and_exchange(self):
        for ticker, (name, exchange) in US_HARDCODED_TICKERS.items():
            assert name, f"{ticker}: name kosong"
            assert exchange in ("NASDAQ", "NYSE"), f"{ticker}: exchange tidak valid: {exchange}"

    def test_no_jk_suffix(self):
        """Ticker US tidak boleh punya suffix .JK."""
        for ticker in US_HARDCODED_TICKERS:
            assert not ticker.endswith(".JK"), f"{ticker} punya suffix .JK"


# ---------------------------------------------------------------------------
# _ticker_to_instrument_info
# ---------------------------------------------------------------------------

class TestTickerToInstrumentInfo:
    def test_canonical_symbol_format(self):
        info = _ticker_to_instrument_info("AAPL", "Apple Inc.", "NASDAQ")
        assert info.canonical_symbol == "US:AAPL"

    def test_local_symbol(self):
        info = _ticker_to_instrument_info("MSFT", "Microsoft", "NASDAQ")
        assert info.local_symbol == "MSFT"

    def test_currency_usd(self):
        info = _ticker_to_instrument_info("JPM", "JPMorgan", "NYSE")
        assert info.currency == "USD"

    def test_country_us(self):
        info = _ticker_to_instrument_info("GS", "Goldman Sachs", "NYSE")
        assert info.country == "US"

    def test_etf_asset_type(self):
        info = _ticker_to_instrument_info("SPY", "SPDR S&P 500 ETF", "NYSE")
        assert info.asset_type == "ETF"

    def test_equity_asset_type(self):
        info = _ticker_to_instrument_info("AAPL", "Apple Inc.", "NASDAQ")
        assert info.asset_type == "EQUITY"

    def test_timezone_new_york(self):
        info = _ticker_to_instrument_info("TSLA", "Tesla", "NASDAQ")
        assert info.timezone == "America/New_York"


# ---------------------------------------------------------------------------
# run_us_bootstrap
# ---------------------------------------------------------------------------

def _make_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


class TestRunUsBootstrap:
    @pytest.mark.asyncio
    async def test_dry_run_returns_total_tickers(self):
        db = _make_db()
        result = await run_us_bootstrap(db, dry_run=True)
        assert result["dry_run"] is True
        assert result["total_tickers"] >= 80

    @pytest.mark.asyncio
    async def test_dry_run_does_not_commit(self):
        db = _make_db()
        await run_us_bootstrap(db, dry_run=True)
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_tickers_limits_processing(self):
        db = _make_db()
        result = await run_us_bootstrap(db, max_tickers=10, dry_run=True)
        assert result["total_tickers"] == 10

    @pytest.mark.asyncio
    async def test_uses_us_provider(self):
        db = _make_db()

        instrument_mock = MagicMock()
        instrument_mock.id = "uuid-aapl"

        ohlcv_result = MagicMock()
        ohlcv_result.inserted = 5
        ohlcv_result.skipped = 0
        ohlcv_result.validation_errors = []

        with patch("app.ingestion.us_bootstrap.upsert_instrument", new=AsyncMock(return_value=instrument_mock)):
            with patch("app.ingestion.us_bootstrap.ingest_ohlcv", new=AsyncMock(return_value=ohlcv_result)):
                with patch("app.ingestion.us_bootstrap.get_provider_registry") as mock_reg:
                    mock_provider = MagicMock()
                    mock_reg.return_value.get_primary.return_value = mock_provider

                    await run_us_bootstrap(db, max_tickers=2)

        mock_reg.return_value.get_primary.assert_called_once_with("US")

    @pytest.mark.asyncio
    async def test_error_per_ticker_does_not_abort(self):
        db = _make_db()

        call_count = 0

        async def mock_upsert(db, info):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("yfinance timeout")
            m = MagicMock()
            m.id = f"uuid-{info.local_symbol}"
            return m

        ohlcv_result = MagicMock()
        ohlcv_result.inserted = 3
        ohlcv_result.skipped = 0
        ohlcv_result.validation_errors = []

        with patch("app.ingestion.us_bootstrap.upsert_instrument", side_effect=mock_upsert):
            with patch("app.ingestion.us_bootstrap.ingest_ohlcv", new=AsyncMock(return_value=ohlcv_result)):
                with patch("app.ingestion.us_bootstrap.get_provider_registry") as mock_reg:
                    mock_reg.return_value.get_primary.return_value = MagicMock()

                    result = await run_us_bootstrap(db, max_tickers=3)

        # 1 error, 2 berhasil
        assert result["errors"] == 1
        assert result["bars_inserted"] == 6  # 2 × 3

    @pytest.mark.asyncio
    async def test_result_has_expected_keys(self):
        db = _make_db()
        result = await run_us_bootstrap(db, dry_run=True)
        assert "total_tickers" in result
        assert "dry_run" in result
