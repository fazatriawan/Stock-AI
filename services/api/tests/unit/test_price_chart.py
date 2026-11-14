"""
Unit tests FREE-28 — OHLCV price chart endpoint + PriceChart component wiring.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.schemas import PriceBarResponse, PriceHistoryResponse


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestPriceHistoryResponseSchema:
    def _make_bar(self, days_ago: int) -> PriceBarResponse:
        d = date.today() - timedelta(days=days_ago)
        return PriceBarResponse(
            session_date=d,
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            adj_close=103.0,
            volume=1_000_000,
            provider="yfinance",
            freshness_status="FRESH",
            is_adjusted=True,
        )

    def test_response_has_bars(self):
        from app.api.schemas import InstrumentResponse
        instr = MagicMock(spec=InstrumentResponse)
        resp = PriceHistoryResponse(
            instrument=instr,
            bars=[self._make_bar(5), self._make_bar(4), self._make_bar(3)],
            count=3,
            start=date.today() - timedelta(days=10),
            end=date.today(),
            provider="yfinance",
            as_of=__import__("datetime").datetime.utcnow(),
        )
        assert resp.count == 3
        assert len(resp.bars) == 3

    def test_bar_adj_close_optional(self):
        bar = PriceBarResponse(
            session_date=date.today(),
            open=10.0,
            high=11.0,
            low=9.5,
            close=10.5,
            adj_close=None,
            volume=None,
            provider="mock",
            freshness_status="STALE",
            is_adjusted=False,
        )
        assert bar.adj_close is None
        assert bar.close == 10.5

    def test_bar_volume_optional(self):
        bar = PriceBarResponse(
            session_date=date.today(),
            open=None,
            high=None,
            low=None,
            close=10.0,
            adj_close=None,
            volume=None,
            provider="mock",
            freshness_status="STALE",
            is_adjusted=False,
        )
        assert bar.volume is None

    def test_bar_open_high_low_optional(self):
        """OHLCV bars may have NULL OHLC when only close is available."""
        bar = PriceBarResponse(
            session_date=date.today(),
            open=None,
            high=None,
            low=None,
            close=5000.0,
            adj_close=None,
            volume=None,
            provider="mock",
            freshness_status="STALE",
            is_adjusted=False,
        )
        assert bar.open is None
        assert bar.close == 5000.0


# ---------------------------------------------------------------------------
# Endpoint tests — mock DB
# ---------------------------------------------------------------------------

def _make_bar_mock(days_ago: int, provider: str = "yfinance") -> MagicMock:
    b = MagicMock()
    b.session_date = date.today() - timedelta(days=days_ago)
    b.open = 100.0
    b.high = 105.0
    b.low = 99.0
    b.close = 103.0
    b.adj_close = 103.0
    b.volume = 500_000
    b.provider = provider
    b.freshness_status = "FRESH"
    b.is_adjusted = True
    return b


def _make_instrument(symbol: str = "BBCA") -> MagicMock:
    instr = MagicMock()
    instr.id = "uuid-bbca"
    instr.canonical_symbol = symbol
    instr.local_symbol = symbol
    instr.company_name = "Bank Central Asia"
    instr.exchange = "IDX"
    instr.sector = "Banking"
    instr.currency = "IDR"
    instr.country = "ID"
    instr.timezone = "Asia/Jakarta"
    instr.asset_type = "equity"
    instr.industry = None
    instr.status = "active"
    instr.market_cap = None
    instr.last_updated = None
    return instr


def _make_db_with_bars(bars: list) -> MagicMock:
    """Mock DB that returns bars on execute."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = bars
    db.execute = AsyncMock(return_value=result)
    return db


class TestGetPricesEndpoint:
    @pytest.mark.asyncio
    async def test_returns_bars_for_valid_range(self):
        from app.api.routes.stocks import get_prices

        bars = [_make_bar_mock(i) for i in range(30, 0, -1)]
        db = _make_db_with_bars(bars)
        instr = _make_instrument()

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=instr)):
            resp = await get_prices("BBCA", range="1m", adjusted=True, db=db)
        assert resp.count == 30
        assert resp.provider == "yfinance"

    @pytest.mark.asyncio
    async def test_empty_bars_returns_zero_count(self):
        from app.api.routes.stocks import get_prices

        db = _make_db_with_bars([])
        instr = _make_instrument()

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=instr)):
            resp = await get_prices("BBCA", range="1m", adjusted=True, db=db)
        assert resp.count == 0
        assert resp.provider == "unknown"

    @pytest.mark.asyncio
    async def test_range_1y_default(self):
        from app.api.routes.stocks import get_prices

        db = _make_db_with_bars([])
        instr = _make_instrument()

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=instr)):
            resp = await get_prices("BBCA", range="1y", adjusted=True, db=db)
        delta = (resp.end - resp.start).days
        assert 364 <= delta <= 366

    @pytest.mark.asyncio
    async def test_range_5y(self):
        from app.api.routes.stocks import get_prices

        db = _make_db_with_bars([])
        instr = _make_instrument()

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=instr)):
            resp = await get_prices("BBCA", range="5y", adjusted=True, db=db)
        delta = (resp.end - resp.start).days
        assert 1824 <= delta <= 1826

    @pytest.mark.asyncio
    async def test_unknown_symbol_raises_404(self):
        from fastapi import HTTPException
        from app.api.routes.stocks import get_prices
        from app.core.exceptions import DataNotFoundError

        db = MagicMock()

        with patch(
            "app.api.routes.stocks._get_instrument_or_404",
            new=AsyncMock(side_effect=DataNotFoundError("not found")),
        ):
            with pytest.raises((HTTPException, DataNotFoundError)):
                await get_prices("UNKNOWN", range="1y", adjusted=True, db=db)


# ---------------------------------------------------------------------------
# Frontend integration check
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_price_chart_component_exists(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "components" / "stock" / "PriceChart.tsx"
        assert src.exists(), "PriceChart.tsx tidak ditemukan"
        content = src.read_text()
        assert "lightweight-charts" in content
        assert "AreaSeries" in content
        assert "CandlestickSeries" in content
        assert "PriceBar" in content

    def test_explorer_imports_price_chart(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "explorer" / "page.tsx"
        assert src.exists()
        content = src.read_text()
        assert "PriceChart" in content
        assert "priceBars" in content
        assert "priceRange" in content
        assert "chartType" in content

    def test_explorer_has_period_selector(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "explorer" / "page.tsx"
        content = src.read_text()
        for period in ["1m", "3m", "6m", "1y", "2y", "5y"]:
            assert period in content, f"Period {period} tidak ada di Explorer"

    def test_api_ts_has_prices(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        content = src.read_text()
        assert "prices" in content
        assert "PriceBar" in content
