"""
Unit tests FREE-08 — Bulk stale refresh service.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.staleness import RefreshStaleResult, refresh_stale_instruments


# ---------------------------------------------------------------------------
# RefreshStaleResult dataclass
# ---------------------------------------------------------------------------

class TestRefreshStaleResult:
    def test_defaults(self):
        r = RefreshStaleResult(instruments_found=0, instruments_refreshed=0, bars_added=0)
        assert r.errors == []
        assert r.ran_at is not None

    def test_with_errors(self):
        r = RefreshStaleResult(
            instruments_found=3,
            instruments_refreshed=2,
            bars_added=50,
            errors=["BBCA: timeout"],
        )
        assert len(r.errors) == 1


# ---------------------------------------------------------------------------
# refresh_stale_instruments — mock DB
# ---------------------------------------------------------------------------

def _make_db(stale_instrument_ids: list[str], instruments: list):
    db = MagicMock()

    # First execute: stale instrument_ids query
    stale_result = MagicMock()
    stale_result.fetchall.return_value = [(iid,) for iid in stale_instrument_ids]

    # Second execute: Instrument objects query
    instrument_result = MagicMock()
    instrument_result.scalars.return_value.all.return_value = instruments

    db.execute = AsyncMock(side_effect=[stale_result, instrument_result])
    return db


def _make_instrument(symbol: str, exchange: str = "IDX") -> MagicMock:
    instr = MagicMock()
    instr.id = f"uuid-{symbol}"
    instr.canonical_symbol = symbol
    instr.exchange = exchange
    return instr


class TestRefreshStaleInstruments:
    @pytest.mark.asyncio
    async def test_no_stale_returns_zero(self):
        db = _make_db(stale_instrument_ids=[], instruments=[])
        result = await refresh_stale_instruments(db)
        assert result.instruments_found == 0
        assert result.instruments_refreshed == 0
        assert result.bars_added == 0

    @pytest.mark.asyncio
    async def test_refreshes_found_instruments(self):
        instr = _make_instrument("BBCA")
        db = _make_db(["uuid-BBCA"], [instr])

        ingest_result = MagicMock()
        ingest_result.inserted = 10

        with patch("app.ingestion.staleness.ingest_ohlcv", new=AsyncMock(return_value=ingest_result)):
            with patch("app.ingestion.staleness.get_provider_registry") as mock_registry:
                mock_provider = MagicMock()
                mock_registry.return_value.get_primary.return_value = mock_provider

                result = await refresh_stale_instruments(db, days_back=365)

        assert result.instruments_found == 1
        assert result.instruments_refreshed == 1
        assert result.bars_added == 10
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_error_per_instrument_does_not_abort(self):
        """Satu instrumen gagal tidak menghentikan yang lain."""
        instr1 = _make_instrument("BBCA")
        instr2 = _make_instrument("BMRI")
        db = _make_db(["uuid-BBCA", "uuid-BMRI"], [instr1, instr2])

        ok_result = MagicMock()
        ok_result.inserted = 5

        call_count = 0

        async def mock_ingest(db, instr, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if instr.canonical_symbol == "BBCA":
                raise ConnectionError("yfinance timeout")
            return ok_result

        with patch("app.ingestion.staleness.ingest_ohlcv", side_effect=mock_ingest):
            with patch("app.ingestion.staleness.get_provider_registry") as mock_registry:
                mock_provider = MagicMock()
                mock_registry.return_value.get_primary.return_value = mock_provider

                result = await refresh_stale_instruments(db)

        assert result.instruments_found == 2
        assert result.instruments_refreshed == 1  # hanya BMRI berhasil
        assert result.bars_added == 5
        assert len(result.errors) == 1
        assert "BBCA" in result.errors[0]

    @pytest.mark.asyncio
    async def test_uses_idx_provider_for_idx_exchange(self):
        instr = _make_instrument("BBCA", exchange="IDX")
        db = _make_db(["uuid-BBCA"], [instr])

        ingest_result = MagicMock()
        ingest_result.inserted = 3

        with patch("app.ingestion.staleness.ingest_ohlcv", new=AsyncMock(return_value=ingest_result)):
            with patch("app.ingestion.staleness.get_provider_registry") as mock_registry:
                mock_provider = MagicMock()
                mock_registry.return_value.get_primary.return_value = mock_provider

                await refresh_stale_instruments(db)

        mock_registry.return_value.get_primary.assert_called_once_with("IDX")

    @pytest.mark.asyncio
    async def test_uses_us_provider_for_nasdaq(self):
        instr = _make_instrument("AAPL", exchange="NASDAQ")
        db = _make_db(["uuid-AAPL"], [instr])

        ingest_result = MagicMock()
        ingest_result.inserted = 2

        with patch("app.ingestion.staleness.ingest_ohlcv", new=AsyncMock(return_value=ingest_result)):
            with patch("app.ingestion.staleness.get_provider_registry") as mock_registry:
                mock_provider = MagicMock()
                mock_registry.return_value.get_primary.return_value = mock_provider

                await refresh_stale_instruments(db)

        mock_registry.return_value.get_primary.assert_called_once_with("US")

    @pytest.mark.asyncio
    async def test_ran_at_is_utc(self):
        db = _make_db([], [])
        result = await refresh_stale_instruments(db)
        assert result.ran_at.tzinfo is not None


# ---------------------------------------------------------------------------
# ohlcv.py upsert includes freshness_status in update set
# ---------------------------------------------------------------------------

class TestOHLCVUpsertFreshnessStatus:
    def test_force_upsert_updates_freshness(self):
        """
        Verifikasi bahwa upsert force=True menyertakan freshness_status di set_.
        """
        import ast
        import pathlib

        src = pathlib.Path(__file__).parent.parent.parent / "app" / "ingestion" / "ohlcv.py"
        tree = ast.parse(src.read_text())

        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "on_conflict_do_update":
                    for kw in node.keywords:
                        if kw.arg == "set_" and isinstance(kw.value, ast.Dict):
                            keys = [
                                k.s if isinstance(k, ast.Constant) else None
                                for k in kw.value.keys
                            ]
                            if "freshness_status" in keys:
                                found = True
        assert found, "freshness_status tidak ditemukan di on_conflict_do_update set_ di ohlcv.py"


# ---------------------------------------------------------------------------
# RefreshStaleResponse schema
# ---------------------------------------------------------------------------

class TestRefreshStaleResponseSchema:
    def test_schema(self):
        from app.api.schemas import RefreshStaleResponse

        r = RefreshStaleResponse(
            instruments_found=3,
            instruments_refreshed=2,
            bars_added=50,
            errors=["X: timeout"],
            ran_at=datetime.now(tz=timezone.utc),
        )
        assert r.instruments_found == 3
        assert len(r.errors) == 1

    def test_empty_errors(self):
        from app.api.schemas import RefreshStaleResponse

        r = RefreshStaleResponse(
            instruments_found=1,
            instruments_refreshed=1,
            bars_added=10,
            errors=[],
            ran_at=datetime.now(tz=timezone.utc),
        )
        assert r.errors == []
