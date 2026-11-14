"""
Unit tests FREE-25 — Batch instrument refresh endpoint.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.schemas import BatchRefreshItemResult, BatchRefreshResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_instrument(symbol: str = "IDX:BBCA", exchange: str = "IDX") -> MagicMock:
    instr = MagicMock()
    instr.id = "uuid-" + symbol.replace(":", "-")
    instr.canonical_symbol = symbol
    instr.exchange = exchange
    return instr


def _make_fallback_result(bars_added: int = 10, provider: str = "yfinance") -> MagicMock:
    r = MagicMock()
    r.bars_added = bars_added
    r.provider_used = provider
    return r


def _make_db(stale_rows=None) -> MagicMock:
    db = MagicMock()

    # For stale instruments query
    stmt_result = MagicMock()
    stmt_result.all.return_value = stale_rows or []
    db.execute = AsyncMock(return_value=stmt_result)
    db.commit = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestBatchRefreshSchemas:
    def test_item_result_ok(self):
        item = BatchRefreshItemResult(
            canonical_symbol="IDX:BBCA",
            status="ok",
            bars_added=10,
            provider_used="yfinance",
        )
        assert item.status == "ok"
        assert item.bars_added == 10
        assert item.provider_used == "yfinance"
        assert item.message is None

    def test_item_result_error(self):
        item = BatchRefreshItemResult(
            canonical_symbol="IDX:BBCA",
            status="error",
            message="Connection refused",
        )
        assert item.status == "error"
        assert item.bars_added == 0
        assert item.provider_used is None

    def test_item_result_not_found(self):
        item = BatchRefreshItemResult(
            canonical_symbol="UNKNOWN",
            status="not_found",
            message="Instrumen 'UNKNOWN' tidak ditemukan di database",
        )
        assert item.status == "not_found"

    def test_item_result_no_data(self):
        item = BatchRefreshItemResult(
            canonical_symbol="IDX:BBCA",
            status="no_data",
            message="Provider tidak mengembalikan bar baru",
        )
        assert item.status == "no_data"

    def test_response_aggregates(self):
        resp = BatchRefreshResponse(
            results=[
                BatchRefreshItemResult(canonical_symbol="IDX:BBCA", status="ok", bars_added=10),
                BatchRefreshItemResult(canonical_symbol="IDX:BMRI", status="error"),
            ],
            total_requested=2,
            succeeded=1,
            failed=1,
            total_bars_added=10,
            ran_at=datetime.now(tz=timezone.utc),
        )
        assert resp.total_requested == 2
        assert resp.succeeded == 1
        assert resp.failed == 1
        assert resp.total_bars_added == 10


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class TestRefreshBatchEndpoint:
    @pytest.mark.asyncio
    async def test_specific_symbols_success(self):
        """Symbols explicitly provided → semua berhasil."""
        from app.api.routes.data_health import refresh_batch

        instr = _make_instrument("IDX:BBCA")
        fb = _make_fallback_result(bars_added=15)
        db = _make_db()

        with (
            patch("app.api.routes.data_health.resolve_instrument", new=AsyncMock(return_value=instr)),
            patch("app.api.routes.data_health.ingest_with_fallback", new=AsyncMock(return_value=fb)),
        ):
            response = await refresh_batch(symbols=["IDX:BBCA"], limit=10, days_back=365, db=db)

        assert response.total_requested == 1
        assert response.succeeded == 1
        assert response.failed == 0
        assert response.total_bars_added == 15
        assert response.results[0].status == "ok"
        assert response.results[0].provider_used == "yfinance"

    @pytest.mark.asyncio
    async def test_symbol_not_found(self):
        """resolve_instrument returns None → status not_found."""
        from app.api.routes.data_health import refresh_batch

        db = _make_db()

        with patch("app.api.routes.data_health.resolve_instrument", new=AsyncMock(return_value=None)):
            response = await refresh_batch(symbols=["ZZZZ"], limit=10, days_back=365, db=db)

        assert response.results[0].status == "not_found"
        assert response.failed == 1
        assert response.succeeded == 0

    @pytest.mark.asyncio
    async def test_provider_returns_no_bars(self):
        """ingest_with_fallback returns 0 bars → status no_data."""
        from app.api.routes.data_health import refresh_batch

        instr = _make_instrument("IDX:BBCA")
        fb = _make_fallback_result(bars_added=0)
        db = _make_db()

        with (
            patch("app.api.routes.data_health.resolve_instrument", new=AsyncMock(return_value=instr)),
            patch("app.api.routes.data_health.ingest_with_fallback", new=AsyncMock(return_value=fb)),
        ):
            response = await refresh_batch(symbols=["IDX:BBCA"], limit=10, days_back=365, db=db)

        assert response.results[0].status == "no_data"
        assert response.total_bars_added == 0

    @pytest.mark.asyncio
    async def test_provider_returns_none(self):
        """ingest_with_fallback returns None → status no_data."""
        from app.api.routes.data_health import refresh_batch

        instr = _make_instrument("IDX:BBCA")
        db = _make_db()

        with (
            patch("app.api.routes.data_health.resolve_instrument", new=AsyncMock(return_value=instr)),
            patch("app.api.routes.data_health.ingest_with_fallback", new=AsyncMock(return_value=None)),
        ):
            response = await refresh_batch(symbols=["IDX:BBCA"], limit=10, days_back=365, db=db)

        assert response.results[0].status == "no_data"

    @pytest.mark.asyncio
    async def test_provider_raises_exception(self):
        """Provider throws → status error, tidak crash endpoint."""
        from app.api.routes.data_health import refresh_batch

        instr = _make_instrument("IDX:BBCA")
        db = _make_db()

        with (
            patch("app.api.routes.data_health.resolve_instrument", new=AsyncMock(return_value=instr)),
            patch("app.api.routes.data_health.ingest_with_fallback", new=AsyncMock(side_effect=RuntimeError("timeout"))),
        ):
            response = await refresh_batch(symbols=["IDX:BBCA"], limit=10, days_back=365, db=db)

        assert response.results[0].status == "error"
        assert "timeout" in (response.results[0].message or "")
        assert response.failed == 1

    @pytest.mark.asyncio
    async def test_multiple_symbols_mixed_results(self):
        """3 simbol: 1 ok, 1 not_found, 1 error."""
        from app.api.routes.data_health import refresh_batch

        instr_ok = _make_instrument("IDX:BBCA")
        instr_err = _make_instrument("IDX:BMRI")
        fb_ok = _make_fallback_result(bars_added=5)

        resolve_map = {
            "IDX:BBCA": instr_ok,
            "ZZZZ": None,
            "IDX:BMRI": instr_err,
        }

        ingest_call_count = 0

        async def mock_resolve(db, sym):
            return resolve_map.get(sym)

        async def mock_ingest(db, instr, market, start, end, force):
            nonlocal ingest_call_count
            ingest_call_count += 1
            if instr.canonical_symbol == "IDX:BMRI":
                raise RuntimeError("provider error")
            return fb_ok

        db = _make_db()

        with (
            patch("app.api.routes.data_health.resolve_instrument", new=mock_resolve),
            patch("app.api.routes.data_health.ingest_with_fallback", new=mock_ingest),
        ):
            response = await refresh_batch(
                symbols=["IDX:BBCA", "ZZZZ", "IDX:BMRI"],
                limit=10,
                days_back=365,
                db=db,
            )

        assert response.total_requested == 3
        assert response.succeeded == 1
        assert response.failed == 2
        assert response.total_bars_added == 5

    @pytest.mark.asyncio
    async def test_empty_symbols_queries_stale(self):
        """symbols=[] → query DB untuk instrumen stale."""
        from app.api.routes.data_health import refresh_batch

        # Stale row mock
        stale_row = MagicMock()
        stale_row.canonical_symbol = "IDX:BBCA"

        stale_result = MagicMock()
        stale_result.all.return_value = [stale_row]

        db = MagicMock()
        db.execute = AsyncMock(return_value=stale_result)
        db.commit = AsyncMock()

        instr = _make_instrument("IDX:BBCA")
        fb = _make_fallback_result(bars_added=8)

        with (
            patch("app.api.routes.data_health.resolve_instrument", new=AsyncMock(return_value=instr)),
            patch("app.api.routes.data_health.ingest_with_fallback", new=AsyncMock(return_value=fb)),
        ):
            response = await refresh_batch(symbols=[], limit=5, days_back=365, db=db)

        assert response.total_requested == 1
        assert response.succeeded == 1

    @pytest.mark.asyncio
    async def test_db_commit_called(self):
        """db.commit() dipanggil setelah semua refresh."""
        from app.api.routes.data_health import refresh_batch

        instr = _make_instrument("IDX:BBCA")
        fb = _make_fallback_result(bars_added=3)
        db = _make_db()

        with (
            patch("app.api.routes.data_health.resolve_instrument", new=AsyncMock(return_value=instr)),
            patch("app.api.routes.data_health.ingest_with_fallback", new=AsyncMock(return_value=fb)),
        ):
            await refresh_batch(symbols=["IDX:BBCA"], limit=10, days_back=365, db=db)

        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_us_market_passed_to_ingest(self):
        """Instrumen US → market='US' diteruskan ke ingest_with_fallback."""
        from app.api.routes.data_health import refresh_batch

        instr = _make_instrument("US:AAPL", exchange="US")
        fb = _make_fallback_result(bars_added=20)
        db = _make_db()

        captured: list[str] = []

        async def mock_ingest(db, instr, market, start, end, force):
            captured.append(market)
            return fb

        with (
            patch("app.api.routes.data_health.resolve_instrument", new=AsyncMock(return_value=instr)),
            patch("app.api.routes.data_health.ingest_with_fallback", new=mock_ingest),
        ):
            await refresh_batch(symbols=["US:AAPL"], limit=10, days_back=365, db=db)

        assert captured == ["US"]


# ---------------------------------------------------------------------------
# AST check — api.ts + settings page
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_batch_refresh_types_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "BatchRefreshItemResult" in content
        assert "BatchRefreshResponse" in content
        assert "refreshBatch" in content
        assert "/data/refresh-batch" in content

    def test_segarkan_semua_button_in_settings(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "settings" / "page.tsx"
        if not src.exists():
            pytest.skip("settings/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "Segarkan Semua" in content
        assert "handleRefreshAll" in content
        assert "refreshBatch" in content
        assert "refreshResult" in content
