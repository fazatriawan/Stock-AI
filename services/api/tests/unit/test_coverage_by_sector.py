"""
Unit tests FREE-27 — Data coverage by sector/exchange endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.schemas import (
    CoverageBySectorResponse,
    ExchangeCoverageRow,
    SectorCoverageRow,
)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestCoverageBySectorSchemas:
    def test_exchange_row(self):
        row = ExchangeCoverageRow(
            exchange="IDX",
            total_instruments=50,
            instruments_with_fresh=45,
            fresh_bars=12000,
            stale_bars=1000,
            total_bars=13000,
            fresh_pct=92.3,
        )
        assert row.exchange == "IDX"
        assert row.fresh_pct == 92.3

    def test_sector_row(self):
        row = SectorCoverageRow(
            sector="Banking",
            exchange="IDX",
            instrument_count=10,
            fresh_bars=5000,
            stale_bars=200,
            total_bars=5200,
            fresh_pct=96.2,
        )
        assert row.sector == "Banking"
        assert row.instrument_count == 10

    def test_response_has_both_lists(self):
        resp = CoverageBySectorResponse(
            by_exchange=[
                ExchangeCoverageRow(
                    exchange="IDX",
                    total_instruments=10,
                    instruments_with_fresh=8,
                    fresh_bars=1000,
                    stale_bars=100,
                    total_bars=1100,
                    fresh_pct=90.9,
                )
            ],
            by_sector=[],
            checked_at=datetime.now(tz=timezone.utc),
        )
        assert len(resp.by_exchange) == 1
        assert resp.by_sector == []


# ---------------------------------------------------------------------------
# Endpoint tests — mock DB
# ---------------------------------------------------------------------------

def _make_ex_row(exchange: str, instruments: int = 5, fresh: int = 400,
                 stale: int = 50, total: int = 450) -> MagicMock:
    r = MagicMock()
    r.exchange = exchange
    r.total_instruments = instruments
    r.fresh_bars = fresh
    r.stale_bars = stale
    r.total_bars = total
    return r


def _make_sec_row(sector: str, exchange: str = "IDX",
                  instruments: int = 3, fresh: int = 200,
                  stale: int = 20, total: int = 220) -> MagicMock:
    r = MagicMock()
    r.sector = sector
    r.exchange = exchange
    r.instrument_count = instruments
    r.fresh_bars = fresh
    r.stale_bars = stale
    r.total_bars = total
    return r


def _make_db(ex_rows=None, fresh_map_rows=None, sec_rows=None):
    """Return a mock db that sequences three execute() results."""
    db = MagicMock()

    ex_result = MagicMock()
    ex_result.all.return_value = ex_rows or []

    fresh_result = MagicMock()
    fresh_result.all.return_value = fresh_map_rows or []

    sec_result = MagicMock()
    sec_result.all.return_value = sec_rows or []

    db.execute = AsyncMock(side_effect=[ex_result, fresh_result, sec_result])
    return db


class TestCoverageBySectorEndpoint:
    @pytest.mark.asyncio
    async def test_basic_response_structure(self):
        from app.api.routes.data_health import get_coverage_by_sector

        ex_row = _make_ex_row("IDX", instruments=20, fresh=10000, stale=500, total=10500)

        # fresh map row: exchange + with_fresh count
        fm_row = MagicMock()
        fm_row.exchange = "IDX"
        fm_row.with_fresh = 18

        sec_row = _make_sec_row("Banking", "IDX")

        db = _make_db(ex_rows=[ex_row], fresh_map_rows=[fm_row], sec_rows=[sec_row])
        response = await get_coverage_by_sector(db=db)

        assert len(response.by_exchange) == 1
        assert len(response.by_sector) == 1
        assert response.by_exchange[0].exchange == "IDX"

    @pytest.mark.asyncio
    async def test_instruments_with_fresh_populated(self):
        from app.api.routes.data_health import get_coverage_by_sector

        ex_row = _make_ex_row("IDX", instruments=20)
        fm_row = MagicMock()
        fm_row.exchange = "IDX"
        fm_row.with_fresh = 15

        db = _make_db(ex_rows=[ex_row], fresh_map_rows=[fm_row], sec_rows=[])
        response = await get_coverage_by_sector(db=db)

        assert response.by_exchange[0].instruments_with_fresh == 15

    @pytest.mark.asyncio
    async def test_missing_fresh_map_defaults_to_zero(self):
        """Exchange with no FRESH bars gets instruments_with_fresh=0."""
        from app.api.routes.data_health import get_coverage_by_sector

        ex_row = _make_ex_row("US", instruments=10)
        # fresh_map_rows empty → no match for US
        db = _make_db(ex_rows=[ex_row], fresh_map_rows=[], sec_rows=[])
        response = await get_coverage_by_sector(db=db)

        assert response.by_exchange[0].instruments_with_fresh == 0

    @pytest.mark.asyncio
    async def test_fresh_pct_calculated(self):
        from app.api.routes.data_health import get_coverage_by_sector

        ex_row = _make_ex_row("IDX", fresh=750, stale=250, total=1000)
        db = _make_db(ex_rows=[ex_row], fresh_map_rows=[], sec_rows=[])
        response = await get_coverage_by_sector(db=db)

        assert response.by_exchange[0].fresh_pct == 75.0

    @pytest.mark.asyncio
    async def test_zero_bars_gives_zero_pct(self):
        from app.api.routes.data_health import get_coverage_by_sector

        ex_row = _make_ex_row("IDX", fresh=0, stale=0, total=0)
        db = _make_db(ex_rows=[ex_row], fresh_map_rows=[], sec_rows=[])
        response = await get_coverage_by_sector(db=db)

        assert response.by_exchange[0].fresh_pct == 0.0

    @pytest.mark.asyncio
    async def test_multiple_exchanges(self):
        from app.api.routes.data_health import get_coverage_by_sector

        idx_row = _make_ex_row("IDX", instruments=50)
        us_row = _make_ex_row("US", instruments=20)

        db = _make_db(ex_rows=[idx_row, us_row], fresh_map_rows=[], sec_rows=[])
        response = await get_coverage_by_sector(db=db)

        exchanges = [r.exchange for r in response.by_exchange]
        assert "IDX" in exchanges
        assert "US" in exchanges

    @pytest.mark.asyncio
    async def test_sector_null_becomes_unknown(self):
        """Rows with sector=None should appear as 'Unknown'."""
        from app.api.routes.data_health import get_coverage_by_sector

        # In the actual query coalesce() handles NULL at SQL level, so sector is "Unknown"
        sec_row = _make_sec_row("Unknown", "IDX")

        db = _make_db(ex_rows=[], fresh_map_rows=[], sec_rows=[sec_row])
        response = await get_coverage_by_sector(db=db)

        assert response.by_sector[0].sector == "Unknown"

    @pytest.mark.asyncio
    async def test_empty_database_returns_empty_lists(self):
        from app.api.routes.data_health import get_coverage_by_sector

        db = _make_db(ex_rows=[], fresh_map_rows=[], sec_rows=[])
        response = await get_coverage_by_sector(db=db)

        assert response.by_exchange == []
        assert response.by_sector == []

    @pytest.mark.asyncio
    async def test_checked_at_set(self):
        from app.api.routes.data_health import get_coverage_by_sector

        db = _make_db()
        before = datetime.now(tz=timezone.utc)
        response = await get_coverage_by_sector(db=db)
        after = datetime.now(tz=timezone.utc)

        assert before <= response.checked_at <= after


# ---------------------------------------------------------------------------
# AST check — api.ts + settings page
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_coverage_types_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "ExchangeCoverageRow" in content
        assert "SectorCoverageRow" in content
        assert "CoverageBySectorResponse" in content
        assert "coverageBySector" in content
        assert "/data/coverage-by-sector" in content

    def test_sector_coverage_section_in_settings(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "settings" / "page.tsx"
        if not src.exists():
            pytest.skip("settings/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "SectorCoverageSection" in content
        assert "Coverage Data" in content
        assert "coverageBySector" in content
        assert "by_exchange" in content
        assert "by_sector" in content
