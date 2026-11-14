"""
Unit tests FREE-18 — Gap auto-healer.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analytics.gap_healer import HealResult, heal_data_gaps


# ---------------------------------------------------------------------------
# HealResult dataclass
# ---------------------------------------------------------------------------

class TestHealResult:
    def test_defaults(self):
        r = HealResult(instruments_found=0, instruments_healed=0, bars_added=0)
        assert r.errors == []
        assert r.ran_at is not None
        assert r.ran_at.tzinfo is not None

    def test_with_errors(self):
        r = HealResult(
            instruments_found=3,
            instruments_healed=2,
            bars_added=50,
            errors=["IDX:BBCA: semua provider kosong"],
        )
        assert len(r.errors) == 1
        assert r.instruments_healed == 2


# ---------------------------------------------------------------------------
# heal_data_gaps — mock detect_data_gaps + ingest_with_fallback
# ---------------------------------------------------------------------------

def _make_gap_report(symbol: str, severity: str, exchange: str = "IDX") -> MagicMock:
    r = MagicMock()
    r.instrument_id = f"uuid-{symbol}"
    r.canonical_symbol = symbol
    r.exchange = exchange
    r.severity = severity
    r.gap_pct = 30.0 if severity == "CRITICAL" else 15.0
    r.first_date = date(2024, 1, 2)
    return r


def _make_detect_result(reports: list) -> MagicMock:
    result = MagicMock()
    result.reports = reports
    result.instruments_checked = len(reports)
    result.with_gaps = sum(1 for r in reports if r.severity != "OK")
    return result


def _make_instrument(iid: str, symbol: str, exchange: str = "IDX") -> MagicMock:
    instr = MagicMock()
    instr.id = iid
    instr.canonical_symbol = symbol
    instr.exchange = exchange
    return instr


def _make_fb_result(inserted: int = 5, provider: str = "yfinance") -> MagicMock:
    from app.ingestion.provider_fallback import FallbackIngestResult
    ohlcv = MagicMock()
    ohlcv.inserted = inserted
    return FallbackIngestResult(ohlcv=ohlcv, provider_used=provider, fallback_used=False)


class TestHealDataGaps:
    @pytest.mark.asyncio
    async def test_no_gaps_returns_zero(self):
        db = MagicMock()
        empty_detect = _make_detect_result([])

        with patch("app.analytics.gap_healer.detect_data_gaps", new=AsyncMock(return_value=empty_detect)):
            result = await heal_data_gaps(db)

        assert result.instruments_found == 0
        assert result.instruments_healed == 0
        assert result.bars_added == 0

    @pytest.mark.asyncio
    async def test_ok_severity_skipped(self):
        """Gap dengan severity OK tidak di-heal."""
        db = MagicMock()
        ok_report = _make_gap_report("IDX:BBCA", "OK")
        detect_result = _make_detect_result([ok_report])

        with patch("app.analytics.gap_healer.detect_data_gaps", new=AsyncMock(return_value=detect_result)):
            with patch("app.analytics.gap_healer.ingest_with_fallback") as mock_ingest:
                result = await heal_data_gaps(db)

        assert result.instruments_found == 0
        mock_ingest.assert_not_called()

    @pytest.mark.asyncio
    async def test_critical_instrument_healed(self):
        db = MagicMock()
        gap = _make_gap_report("IDX:BBCA", "CRITICAL")
        detect_result = _make_detect_result([gap])

        instr = _make_instrument("uuid-IDX:BBCA", "IDX:BBCA")
        instr_query_result = MagicMock()
        instr_query_result.scalars.return_value.all.return_value = [instr]
        db.execute = AsyncMock(return_value=instr_query_result)

        fb_ok = _make_fb_result(inserted=30)

        with patch("app.analytics.gap_healer.detect_data_gaps", new=AsyncMock(return_value=detect_result)):
            with patch("app.analytics.gap_healer.ingest_with_fallback", new=AsyncMock(return_value=fb_ok)):
                result = await heal_data_gaps(db)

        assert result.instruments_found == 1
        assert result.instruments_healed == 1
        assert result.bars_added == 30
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_provider_empty_counts_as_error(self):
        db = MagicMock()
        gap = _make_gap_report("IDX:BMRI", "WARNING")
        detect_result = _make_detect_result([gap])

        instr = _make_instrument("uuid-IDX:BMRI", "IDX:BMRI")
        instr_query_result = MagicMock()
        instr_query_result.scalars.return_value.all.return_value = [instr]
        db.execute = AsyncMock(return_value=instr_query_result)

        with patch("app.analytics.gap_healer.detect_data_gaps", new=AsyncMock(return_value=detect_result)):
            with patch("app.analytics.gap_healer.ingest_with_fallback", new=AsyncMock(return_value=None)):
                result = await heal_data_gaps(db)

        assert result.instruments_healed == 0
        assert len(result.errors) == 1
        assert "IDX:BMRI" in result.errors[0]

    @pytest.mark.asyncio
    async def test_error_per_instrument_does_not_abort(self):
        """Satu instrumen error tidak menghentikan yang lain."""
        db = MagicMock()
        gap1 = _make_gap_report("IDX:BBCA", "CRITICAL")
        gap2 = _make_gap_report("IDX:BMRI", "WARNING")
        detect_result = _make_detect_result([gap1, gap2])

        instr1 = _make_instrument("uuid-IDX:BBCA", "IDX:BBCA")
        instr2 = _make_instrument("uuid-IDX:BMRI", "IDX:BMRI")
        instr_query_result = MagicMock()
        instr_query_result.scalars.return_value.all.return_value = [instr1, instr2]
        db.execute = AsyncMock(return_value=instr_query_result)

        fb_ok = _make_fb_result(inserted=10)

        async def mock_ingest(db, instr, market, start, end, force=False, skip_mock=True):
            if instr.canonical_symbol == "IDX:BBCA":
                raise ConnectionError("timeout")
            return fb_ok

        with patch("app.analytics.gap_healer.detect_data_gaps", new=AsyncMock(return_value=detect_result)):
            with patch("app.analytics.gap_healer.ingest_with_fallback", side_effect=mock_ingest):
                result = await heal_data_gaps(db)

        assert result.instruments_found == 2
        assert result.instruments_healed == 1
        assert result.bars_added == 10
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_us_market_routing(self):
        """Instrumen US dikirim ke market='US'."""
        db = MagicMock()
        gap = _make_gap_report("AAPL", "CRITICAL", exchange="NASDAQ")
        detect_result = _make_detect_result([gap])

        instr = _make_instrument("uuid-AAPL", "AAPL", exchange="NASDAQ")
        instr_query_result = MagicMock()
        instr_query_result.scalars.return_value.all.return_value = [instr]
        db.execute = AsyncMock(return_value=instr_query_result)

        fb_ok = _make_fb_result(inserted=5)
        mock_ingest = AsyncMock(return_value=fb_ok)

        with patch("app.analytics.gap_healer.detect_data_gaps", new=AsyncMock(return_value=detect_result)):
            with patch("app.analytics.gap_healer.ingest_with_fallback", mock_ingest):
                await heal_data_gaps(db)

        # Verifikasi market="US" dikirim ke ingest_with_fallback
        call_args = mock_ingest.call_args
        assert call_args[0][2] == "US" or call_args.kwargs.get("market") == "US"

    @pytest.mark.asyncio
    async def test_uses_first_date_as_start(self):
        """start ingest = gap.first_date, bukan today - 365."""
        db = MagicMock()
        first = date(2022, 6, 1)
        gap = _make_gap_report("IDX:TLKM", "CRITICAL")
        gap.first_date = first
        detect_result = _make_detect_result([gap])

        instr = _make_instrument("uuid-IDX:TLKM", "IDX:TLKM")
        instr_query_result = MagicMock()
        instr_query_result.scalars.return_value.all.return_value = [instr]
        db.execute = AsyncMock(return_value=instr_query_result)

        fb_ok = _make_fb_result(inserted=1)
        mock_ingest = AsyncMock(return_value=fb_ok)

        with patch("app.analytics.gap_healer.detect_data_gaps", new=AsyncMock(return_value=detect_result)):
            with patch("app.analytics.gap_healer.ingest_with_fallback", mock_ingest):
                await heal_data_gaps(db)

        call_args = mock_ingest.call_args
        start_arg = call_args[0][3] if len(call_args[0]) > 3 else call_args.kwargs.get("start")
        assert start_arg == first


# ---------------------------------------------------------------------------
# AST check: api.ts + settings page
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_heal_gaps_result_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "HealGapsResult" in content
        assert "healGaps" in content

    def test_heal_button_in_settings(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "settings" / "page.tsx"
        if not src.exists():
            pytest.skip("settings/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "healGaps" in content
        assert "Perbaiki Otomatis" in content
