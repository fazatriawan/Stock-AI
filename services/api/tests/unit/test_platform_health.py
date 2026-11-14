"""
Unit tests FREE-21 — Platform health summary.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analytics.platform_health import (
    PlatformHealthResult,
    _grade,
    compute_platform_health,
)


# ---------------------------------------------------------------------------
# _grade helper
# ---------------------------------------------------------------------------

class TestGrade:
    def test_a_at_90(self):
        assert _grade(90) == "A"
        assert _grade(100) == "A"

    def test_b_range(self):
        assert _grade(75) == "B"
        assert _grade(89) == "B"

    def test_c_range(self):
        assert _grade(55) == "C"
        assert _grade(74) == "C"

    def test_d_range(self):
        assert _grade(35) == "D"
        assert _grade(54) == "D"

    def test_f_below_35(self):
        assert _grade(0) == "F"
        assert _grade(34) == "F"


# ---------------------------------------------------------------------------
# compute_platform_health — mock all external deps
# ---------------------------------------------------------------------------

def _make_db(total_bars: int = 1000, fresh_bars: int = 950):
    """Mock AsyncSession returning fake price_bars counts."""
    db = MagicMock()
    row = MagicMock()
    row.total = total_bars
    row.fresh = fresh_bars
    result = MagicMock()
    result.one.return_value = row
    db.execute = AsyncMock(return_value=result)
    return db


def _make_gap_result(critical: int = 0, warning: int = 0):
    reports = []
    for _ in range(critical):
        r = MagicMock()
        r.severity = "CRITICAL"
        reports.append(r)
    for _ in range(warning):
        r = MagicMock()
        r.severity = "WARNING"
        reports.append(r)
    result = MagicMock()
    result.reports = reports
    return result


def _make_quota_stats(exhausted_names: list[str] = None):
    stats = []
    for name in (exhausted_names or []):
        s = MagicMock()
        s.provider_name = name
        s.quota_exhausted = True
        stats.append(s)
    return stats


def _make_job_records(statuses: list[str]):
    records = []
    for s in statuses:
        r = MagicMock()
        r.status = s
        r.job_name = f"job_{s}"
        records.append(r)
    return records


class TestComputePlatformHealth:
    @pytest.mark.asyncio
    async def test_perfect_score_no_issues(self):
        db = _make_db(total_bars=1000, fresh_bars=1000)
        gap_result = _make_gap_result()
        quota_stats = _make_quota_stats()
        job_records = _make_job_records(["ok", "ok"])

        with patch("app.analytics.platform_health.detect_data_gaps", new=AsyncMock(return_value=gap_result)):
            with patch("app.analytics.platform_health.get_quota_tracker") as mock_qt:
                mock_qt.return_value.all_stats.return_value = quota_stats
                with patch("app.analytics.platform_health.get_job_history_tracker") as mock_jt:
                    mock_jt.return_value.all_last_runs.return_value = job_records
                    result = await compute_platform_health(db)

        assert result.overall_score == 100
        assert result.grade == "A"
        assert result.freshness.score == 40
        assert result.gaps.score == 25
        assert result.quota.score == 20
        assert result.jobs.score == 15

    @pytest.mark.asyncio
    async def test_critical_gaps_reduce_score(self):
        db = _make_db(total_bars=1000, fresh_bars=1000)
        gap_result = _make_gap_result(critical=3)  # 3 × -5 = -15
        quota_stats = _make_quota_stats()
        job_records = _make_job_records(["ok"])

        with patch("app.analytics.platform_health.detect_data_gaps", new=AsyncMock(return_value=gap_result)):
            with patch("app.analytics.platform_health.get_quota_tracker") as mock_qt:
                mock_qt.return_value.all_stats.return_value = quota_stats
                with patch("app.analytics.platform_health.get_job_history_tracker") as mock_jt:
                    mock_jt.return_value.all_last_runs.return_value = job_records
                    result = await compute_platform_health(db)

        assert result.gaps.score == 10  # 25 - 15
        assert result.gaps.critical_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_quota_reduces_score(self):
        db = _make_db(total_bars=500, fresh_bars=500)
        gap_result = _make_gap_result()
        quota_stats = _make_quota_stats(exhausted_names=["yfinance"])
        job_records = _make_job_records(["ok"])

        with patch("app.analytics.platform_health.detect_data_gaps", new=AsyncMock(return_value=gap_result)):
            with patch("app.analytics.platform_health.get_quota_tracker") as mock_qt:
                mock_qt.return_value.all_stats.return_value = quota_stats
                with patch("app.analytics.platform_health.get_job_history_tracker") as mock_jt:
                    mock_jt.return_value.all_last_runs.return_value = job_records
                    result = await compute_platform_health(db)

        assert result.quota.score == 10
        assert "yfinance" in result.quota.exhausted_providers

    @pytest.mark.asyncio
    async def test_job_errors_reduce_score(self):
        db = _make_db()
        gap_result = _make_gap_result()
        quota_stats = _make_quota_stats()
        job_records = _make_job_records(["ok", "error", "error"])

        with patch("app.analytics.platform_health.detect_data_gaps", new=AsyncMock(return_value=gap_result)):
            with patch("app.analytics.platform_health.get_quota_tracker") as mock_qt:
                mock_qt.return_value.all_stats.return_value = quota_stats
                with patch("app.analytics.platform_health.get_job_history_tracker") as mock_jt:
                    mock_jt.return_value.all_last_runs.return_value = job_records
                    result = await compute_platform_health(db)

        assert result.jobs.score == 5  # 15 - 10
        assert result.jobs.error_count == 2
        assert result.jobs.last_error_job is not None

    @pytest.mark.asyncio
    async def test_low_freshness_reduces_score(self):
        db = _make_db(total_bars=1000, fresh_bars=500)  # 50% fresh → 20/40
        gap_result = _make_gap_result()
        quota_stats = _make_quota_stats()
        job_records = _make_job_records([])

        with patch("app.analytics.platform_health.detect_data_gaps", new=AsyncMock(return_value=gap_result)):
            with patch("app.analytics.platform_health.get_quota_tracker") as mock_qt:
                mock_qt.return_value.all_stats.return_value = quota_stats
                with patch("app.analytics.platform_health.get_job_history_tracker") as mock_jt:
                    mock_jt.return_value.all_last_runs.return_value = job_records
                    result = await compute_platform_health(db)

        assert result.freshness.score == 20
        assert result.freshness.fresh_pct == 50.0

    @pytest.mark.asyncio
    async def test_no_bars_treated_as_100pct_fresh(self):
        """DB vuoto — fresh_pct default 100%."""
        db = _make_db(total_bars=0, fresh_bars=0)
        gap_result = _make_gap_result()
        quota_stats = _make_quota_stats()
        job_records = []

        with patch("app.analytics.platform_health.detect_data_gaps", new=AsyncMock(return_value=gap_result)):
            with patch("app.analytics.platform_health.get_quota_tracker") as mock_qt:
                mock_qt.return_value.all_stats.return_value = quota_stats
                with patch("app.analytics.platform_health.get_job_history_tracker") as mock_jt:
                    mock_jt.return_value.all_last_runs.return_value = job_records
                    result = await compute_platform_health(db)

        assert result.freshness.fresh_pct == 100.0
        assert result.freshness.score == 40

    @pytest.mark.asyncio
    async def test_gap_deduction_capped_at_25(self):
        db = _make_db()
        gap_result = _make_gap_result(critical=10)  # 10 × 5 = 50 → capped at 25
        quota_stats = _make_quota_stats()
        job_records = []

        with patch("app.analytics.platform_health.detect_data_gaps", new=AsyncMock(return_value=gap_result)):
            with patch("app.analytics.platform_health.get_quota_tracker") as mock_qt:
                mock_qt.return_value.all_stats.return_value = quota_stats
                with patch("app.analytics.platform_health.get_job_history_tracker") as mock_jt:
                    mock_jt.return_value.all_last_runs.return_value = job_records
                    result = await compute_platform_health(db)

        assert result.gaps.score == 0

    @pytest.mark.asyncio
    async def test_job_deduction_capped_at_15(self):
        db = _make_db()
        gap_result = _make_gap_result()
        quota_stats = _make_quota_stats()
        job_records = _make_job_records(["error"] * 10)

        with patch("app.analytics.platform_health.detect_data_gaps", new=AsyncMock(return_value=gap_result)):
            with patch("app.analytics.platform_health.get_quota_tracker") as mock_qt:
                mock_qt.return_value.all_stats.return_value = quota_stats
                with patch("app.analytics.platform_health.get_job_history_tracker") as mock_jt:
                    mock_jt.return_value.all_last_runs.return_value = job_records
                    result = await compute_platform_health(db)

        assert result.jobs.score == 0

    @pytest.mark.asyncio
    async def test_result_has_computed_at_utc(self):
        db = _make_db()
        gap_result = _make_gap_result()

        with patch("app.analytics.platform_health.detect_data_gaps", new=AsyncMock(return_value=gap_result)):
            with patch("app.analytics.platform_health.get_quota_tracker") as mock_qt:
                mock_qt.return_value.all_stats.return_value = []
                with patch("app.analytics.platform_health.get_job_history_tracker") as mock_jt:
                    mock_jt.return_value.all_last_runs.return_value = []
                    result = await compute_platform_health(db)

        assert result.computed_at.tzinfo is not None


# ---------------------------------------------------------------------------
# AST check — api.ts + settings page
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_platform_health_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "PlatformHealthSummary" in content
        assert "healthSummary" in content

    def test_platform_health_widget_in_settings(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "settings" / "page.tsx"
        if not src.exists():
            pytest.skip("settings/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "PlatformHealthWidget" in content
        assert "GradeRing" in content
        assert "healthSummary" in content
