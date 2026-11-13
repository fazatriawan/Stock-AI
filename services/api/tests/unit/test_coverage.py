"""
Unit tests FREE-13 — Coverage dashboard (schema + reset-quota logic).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.schemas import CoverageStatusResponse, ResetQuotaResponse


# ---------------------------------------------------------------------------
# CoverageStatusResponse
# ---------------------------------------------------------------------------

class TestCoverageStatusResponse:
    def test_all_fresh(self):
        r = CoverageStatusResponse(
            fresh=5000, stale=0, unavailable=0, quota_exhausted=0,
            other=0, total=5000, stale_pct=0.0,
            unavailable_instruments=0, quota_instruments=0,
        )
        assert r.fresh == 5000
        assert r.stale_pct == 0.0

    def test_mixed_status(self):
        r = CoverageStatusResponse(
            fresh=900, stale=50, unavailable=30, quota_exhausted=10,
            other=10, total=1000, stale_pct=5.0,
            unavailable_instruments=5, quota_instruments=2,
        )
        assert r.total == 1000
        assert r.unavailable_instruments == 5
        assert r.quota_instruments == 2

    def test_zero_state(self):
        r = CoverageStatusResponse(
            fresh=0, stale=0, unavailable=0, quota_exhausted=0,
            other=0, total=0, stale_pct=0.0,
            unavailable_instruments=0, quota_instruments=0,
        )
        assert r.total == 0

    def test_all_unavailable(self):
        r = CoverageStatusResponse(
            fresh=0, stale=0, unavailable=200, quota_exhausted=0,
            other=0, total=200, stale_pct=0.0,
            unavailable_instruments=20, quota_instruments=0,
        )
        assert r.unavailable == 200


# ---------------------------------------------------------------------------
# ResetQuotaResponse
# ---------------------------------------------------------------------------

class TestResetQuotaResponse:
    def test_basic(self):
        r = ResetQuotaResponse(bars_reset=15, ran_at=datetime.now(tz=timezone.utc))
        assert r.bars_reset == 15
        assert r.ran_at.tzinfo is not None

    def test_zero_reset(self):
        r = ResetQuotaResponse(bars_reset=0, ran_at=datetime.now(tz=timezone.utc))
        assert r.bars_reset == 0


# ---------------------------------------------------------------------------
# classify_empty_ingest + mark_empty_bars integration with staleness
# ---------------------------------------------------------------------------

class TestClassifyIntegration:
    """
    Verifikasi bahwa classify_empty_ingest terintegrasi di refresh_stale_instruments.
    Cek via AST — bukan jalankan fungsi — untuk memastikan panggilan ada di source.
    """

    def test_staleness_imports_classify_empty_ingest(self):
        import ast
        import pathlib

        src = pathlib.Path(__file__).parent.parent.parent / "app" / "ingestion" / "staleness.py"
        tree = ast.parse(src.read_text())

        imports_found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "empty_ingest" in node.module:
                    names = [alias.name for alias in node.names]
                    if "classify_empty_ingest" in names and "mark_empty_bars" in names:
                        imports_found = True
        assert imports_found, "classify_empty_ingest / mark_empty_bars tidak diimport di staleness.py"

    def test_staleness_calls_classify(self):
        import ast
        import pathlib

        src = pathlib.Path(__file__).parent.parent.parent / "app" / "ingestion" / "staleness.py"
        tree = ast.parse(src.read_text())

        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    calls.add(func.id)
                elif isinstance(func, ast.Attribute):
                    calls.add(func.attr)

        assert "classify_empty_ingest" in calls, "classify_empty_ingest tidak dipanggil di staleness.py"
        assert "mark_empty_bars" in calls, "mark_empty_bars tidak dipanggil di staleness.py"


# ---------------------------------------------------------------------------
# CoverageStatus type exported from api.ts
# ---------------------------------------------------------------------------

class TestFrontendTypeDefined:
    def test_coverage_status_interface_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "CoverageStatus" in content, "CoverageStatus tidak ditemukan di api.ts"
        assert "quota_exhausted" in content, "quota_exhausted field tidak ada di CoverageStatus"
        assert "resetQuota" in content, "api.data.resetQuota tidak ada di api.ts"
