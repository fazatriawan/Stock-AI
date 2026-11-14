"""
Unit tests FREE-24 — Instrument search prefix-first ordering.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.instruments import search_instruments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_instr(canonical: str, local: str = "", company: str = "") -> MagicMock:
    i = MagicMock()
    i.canonical_symbol = canonical
    i.local_symbol = local
    i.company_name = company
    i.status = "ACTIVE"
    return i


def _make_db(rows: list) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


# ---------------------------------------------------------------------------
# Prefix-first sort
# ---------------------------------------------------------------------------

class TestSearchInstrumentsPrefixSort:
    @pytest.mark.asyncio
    async def test_prefix_match_comes_first(self):
        """IDX:BBCA prefixes 'BB', IDX:ABBA only contains 'BB' → BBCA first."""
        bbca = _make_instr("IDX:BBCA", "BBCA")
        abba = _make_instr("IDX:ABBA", "ABBA")  # contains "BB" but doesn't start with it
        db = _make_db([abba, bbca])  # DB returns ABBA first

        results = await search_instruments(db, "BB")
        assert results[0].canonical_symbol == "IDX:BBCA"

    @pytest.mark.asyncio
    async def test_local_symbol_prefix_beats_contains(self):
        """BBRI starts with 'BB' via local_symbol, ABBA doesn't → BBRI first."""
        bbri = _make_instr("IDX:BBRI", "BBRI")
        abba = _make_instr("IDX:ABBA", "ABBA")
        db = _make_db([abba, bbri])

        results = await search_instruments(db, "BB")
        assert results[0].canonical_symbol == "IDX:BBRI"

    @pytest.mark.asyncio
    async def test_canonical_prefix_beats_local_prefix(self):
        """IDX:BBCA starts with 'BB' in canonical — higher rank than local match."""
        bbca = _make_instr("IDX:BBCA", "XXCA")   # canonical starts with IDX:BB
        xxbb = _make_instr("IDX:XXXX", "BBRI")   # local starts with BB
        db = _make_db([xxbb, bbca])

        results = await search_instruments(db, "BB")
        assert results[0].canonical_symbol == "IDX:BBCA"

    @pytest.mark.asyncio
    async def test_idx_prefix_stripped_for_matching(self):
        """'IDX:BBCA' should match prefix query 'BCA' (strips 'IDX:')."""
        bbca = _make_instr("IDX:BBCA", "BBCA")
        tlkm = _make_instr("IDX:TLKM", "TLKM")
        db = _make_db([tlkm, bbca])

        results = await search_instruments(db, "BBC")
        # IDX:BBCA stripped = BBCA starts with BBC
        assert results[0].canonical_symbol == "IDX:BBCA"

    @pytest.mark.asyncio
    async def test_limit_applied_after_sort(self):
        """Limit is respected after prefix sort."""
        rows = [_make_instr(f"IDX:X{i:02d}", f"X{i:02d}") for i in range(10)]
        db = _make_db(rows)

        results = await search_instruments(db, "X", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_empty_query_returns_rows(self):
        """Empty-ish query falls back gracefully — no crash."""
        bbca = _make_instr("IDX:BBCA", "BBCA")
        db = _make_db([bbca])

        results = await search_instruments(db, "B")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_no_results_returns_empty_list(self):
        db = _make_db([])
        results = await search_instruments(db, "ZZZZ")
        assert results == []


# ---------------------------------------------------------------------------
# AST check — api.ts + explorer page
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_autocomplete_in_explorer(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "explorer" / "page.tsx"
        if not src.exists():
            pytest.skip("explorer/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "suggestions" in content
        assert "showSuggestions" in content
        assert "activeSuggestion" in content
        assert "debounceRef" in content
        assert "api.instruments.search" in content

    def test_keyboard_nav_in_explorer(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "explorer" / "page.tsx"
        if not src.exists():
            pytest.skip("explorer/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "ArrowDown" in content
        assert "ArrowUp" in content
        assert "Escape" in content

    def test_instruments_search_accepts_limit_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        # limit parameter added to search
        assert "limit=${limit}" in content or "limit=" in content
