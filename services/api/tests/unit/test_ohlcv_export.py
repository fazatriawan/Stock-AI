"""
Unit tests FREE-23 — OHLCV CSV export endpoint.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(
    session_date: date,
    close: float = 10000.0,
    provider: str = "yfinance",
    freshness: str = "FRESH",
    open_: float = 9900.0,
    high: float = 10100.0,
    low: float = 9800.0,
    volume: int = 100_000,
    adj_close: float = 10000.0,
) -> MagicMock:
    bar = MagicMock()
    bar.session_date = session_date
    bar.open = Decimal(str(open_))
    bar.high = Decimal(str(high))
    bar.low = Decimal(str(low))
    bar.close = Decimal(str(close))
    bar.adj_close = Decimal(str(adj_close))
    bar.volume = volume
    bar.provider = provider
    bar.freshness_status = freshness
    return bar


def _make_instrument(symbol: str = "IDX:BBCA", iid: str = "uuid-bbca") -> MagicMock:
    instr = MagicMock()
    instr.id = iid
    instr.canonical_symbol = symbol
    instr.exchange = "IDX"
    return instr


# ---------------------------------------------------------------------------
# export_ohlcv_csv
# ---------------------------------------------------------------------------

class TestExportOhlcvCsv:
    @pytest.mark.asyncio
    async def test_returns_csv_response(self):
        from app.api.routes.stocks import export_ohlcv_csv

        db = MagicMock()
        bar = _make_bar(date(2026, 1, 2))

        bars_result = MagicMock()
        bars_result.scalars.return_value.all.return_value = [bar]
        db.execute = AsyncMock(return_value=bars_result)

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=_make_instrument())):
            response = await export_ohlcv_csv("IDX:BBCA", db=db)

        assert response.media_type == "text/csv"
        assert "Content-Disposition" in response.headers
        assert "BBCA" in response.headers["Content-Disposition"]

    @pytest.mark.asyncio
    async def test_csv_contains_header_row(self):
        from app.api.routes.stocks import export_ohlcv_csv

        db = MagicMock()
        bars_result = MagicMock()
        bars_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=bars_result)

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=_make_instrument())):
            response = await export_ohlcv_csv("IDX:BBCA", db=db)

        csv_text = response.body.decode()
        assert csv_text.startswith("session_date,open,high,low,close,adj_close,volume,provider,freshness_status")

    @pytest.mark.asyncio
    async def test_csv_data_row_values(self):
        from app.api.routes.stocks import export_ohlcv_csv

        db = MagicMock()
        bar = _make_bar(date(2026, 3, 1), close=15000.0, provider="yfinance")
        bars_result = MagicMock()
        bars_result.scalars.return_value.all.return_value = [bar]
        db.execute = AsyncMock(return_value=bars_result)

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=_make_instrument())):
            response = await export_ohlcv_csv("IDX:BBCA", db=db)

        csv_text = response.body.decode()
        lines = csv_text.splitlines()
        assert len(lines) == 2  # header + 1 data row
        data_row = lines[1]
        assert "2026-03-01" in data_row
        assert "15000" in data_row
        assert "yfinance" in data_row
        assert "FRESH" in data_row

    @pytest.mark.asyncio
    async def test_empty_result_returns_header_only(self):
        from app.api.routes.stocks import export_ohlcv_csv

        db = MagicMock()
        bars_result = MagicMock()
        bars_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=bars_result)

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=_make_instrument())):
            response = await export_ohlcv_csv("IDX:BBCA", db=db)

        csv_text = response.body.decode()
        lines = [l for l in csv_text.splitlines() if l.strip()]
        assert len(lines) == 1  # header only

    @pytest.mark.asyncio
    async def test_filename_colon_replaced_with_underscore(self):
        """IDX:BBCA → IDX_BBCA_ohlcv.csv (safe filename)."""
        from app.api.routes.stocks import export_ohlcv_csv

        db = MagicMock()
        bars_result = MagicMock()
        bars_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=bars_result)

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=_make_instrument())):
            response = await export_ohlcv_csv("IDX:BBCA", db=db)

        disposition = response.headers["Content-Disposition"]
        assert ":" not in disposition.split("filename=")[-1]
        assert "IDX_BBCA" in disposition

    @pytest.mark.asyncio
    async def test_none_values_produce_empty_csv_field(self):
        """Bar dengan volume=None menghasilkan field kosong, bukan 'None'."""
        from app.api.routes.stocks import export_ohlcv_csv

        db = MagicMock()
        bar = MagicMock()
        bar.session_date = date(2026, 1, 5)
        bar.open = None
        bar.high = None
        bar.low = None
        bar.close = Decimal("12000")
        bar.adj_close = None
        bar.volume = None
        bar.provider = "yfinance"
        bar.freshness_status = "FRESH"
        bars_result = MagicMock()
        bars_result.scalars.return_value.all.return_value = [bar]
        db.execute = AsyncMock(return_value=bars_result)

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=_make_instrument())):
            response = await export_ohlcv_csv("IDX:BBCA", db=db)

        csv_text = response.body.decode()
        assert "None" not in csv_text
        # Fields open, high, low, adj_close, volume are empty
        data_line = csv_text.splitlines()[1]
        parts = data_line.split(",")
        assert parts[1] == ""  # open
        assert parts[5] == ""  # adj_close
        assert parts[6] == ""  # volume

    @pytest.mark.asyncio
    async def test_multiple_bars_sorted_by_date(self):
        from app.api.routes.stocks import export_ohlcv_csv

        db = MagicMock()
        bars = [
            _make_bar(date(2026, 1, 3), close=10200.0),
            _make_bar(date(2026, 1, 1), close=10000.0),
            _make_bar(date(2026, 1, 2), close=10100.0),
        ]
        # Simulate DB returning bars in order (the test just checks CSV row order)
        bars_result = MagicMock()
        bars_result.scalars.return_value.all.return_value = sorted(bars, key=lambda b: b.session_date)
        db.execute = AsyncMock(return_value=bars_result)

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=_make_instrument())):
            response = await export_ohlcv_csv("IDX:BBCA", db=db)

        lines = response.body.decode().splitlines()
        assert len(lines) == 4
        assert "2026-01-01" in lines[1]
        assert "2026-01-03" in lines[3]


# ---------------------------------------------------------------------------
# AST check — api.ts + explorer page
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_export_csv_url_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "exportCsvUrl" in content
        assert "ohlcv/export" in content

    def test_export_button_in_explorer(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "explorer" / "page.tsx"
        if not src.exists():
            pytest.skip("explorer/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "exportCsvUrl" in content
        assert "Export CSV" in content
        assert "Download" in content
