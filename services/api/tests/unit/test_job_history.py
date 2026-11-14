"""
Unit tests FREE-20 — Scheduler job history tracker.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from app.scheduling.job_history import JobHistoryTracker, JobRunRecord, get_job_history_tracker


# ---------------------------------------------------------------------------
# JobRunRecord dataclass
# ---------------------------------------------------------------------------

class TestJobRunRecord:
    def test_defaults(self):
        rec = JobRunRecord(job_name="test_job", started_at=datetime.now(tz=timezone.utc))
        assert rec.status == "running"
        assert rec.finished_at is None
        assert rec.duration_ms is None
        assert rec.summary == {}
        assert rec.error is None

    def test_started_at_is_timezone_aware(self):
        rec = JobRunRecord(job_name="x", started_at=datetime.now(tz=timezone.utc))
        assert rec.started_at.tzinfo is not None


# ---------------------------------------------------------------------------
# JobHistoryTracker
# ---------------------------------------------------------------------------

class TestJobHistoryTracker:
    def test_start_run_returns_record(self):
        tracker = JobHistoryTracker()
        rec = tracker.start_run("my_job")
        assert isinstance(rec, JobRunRecord)
        assert rec.job_name == "my_job"
        assert rec.status == "running"
        assert rec.started_at.tzinfo is not None

    def test_finish_run_updates_record(self):
        tracker = JobHistoryTracker()
        rec = tracker.start_run("my_job")
        tracker.finish_run(rec, status="ok", summary={"count": 5})
        assert rec.status == "ok"
        assert rec.finished_at is not None
        assert rec.duration_ms is not None
        assert rec.duration_ms >= 0
        assert rec.summary == {"count": 5}

    def test_finish_run_error(self):
        tracker = JobHistoryTracker()
        rec = tracker.start_run("failing_job")
        tracker.finish_run(rec, status="error", error="connection_refused")
        assert rec.status == "error"
        assert rec.error == "connection_refused"

    def test_last_run_returns_most_recent(self):
        tracker = JobHistoryTracker()
        rec1 = tracker.start_run("job_a")
        tracker.finish_run(rec1, status="ok")
        rec2 = tracker.start_run("job_a")
        tracker.finish_run(rec2, status="error", error="timeout")

        last = tracker.last_run("job_a")
        assert last is rec2
        assert last.status == "error"

    def test_last_run_unknown_job_returns_none(self):
        tracker = JobHistoryTracker()
        assert tracker.last_run("nonexistent") is None

    def test_multiple_jobs_tracked_independently(self):
        tracker = JobHistoryTracker()
        r1 = tracker.start_run("job_a")
        tracker.finish_run(r1, status="ok")
        r2 = tracker.start_run("job_b")
        tracker.finish_run(r2, status="error", error="boom")

        assert tracker.last_run("job_a").status == "ok"
        assert tracker.last_run("job_b").status == "error"

    def test_all_last_runs_one_per_job(self):
        tracker = JobHistoryTracker()
        for name in ("alpha", "beta", "gamma"):
            rec = tracker.start_run(name)
            tracker.finish_run(rec, status="ok")

        results = tracker.all_last_runs()
        names = {r.job_name for r in results}
        assert names == {"alpha", "beta", "gamma"}

    def test_all_last_runs_sorted_desc(self):
        tracker = JobHistoryTracker()
        for name in ("first", "second", "third"):
            rec = tracker.start_run(name)
            tracker.finish_run(rec, status="ok")

        results = tracker.all_last_runs()
        # Most recent first
        for i in range(len(results) - 1):
            assert results[i].started_at >= results[i + 1].started_at

    def test_max_per_job_ring_buffer(self):
        tracker = JobHistoryTracker(max_per_job=3)
        for i in range(5):
            rec = tracker.start_run("job")
            tracker.finish_run(rec, status="ok", summary={"i": i})

        history = tracker.run_history("job")
        assert len(history) == 3
        # Oldest evicted — only last 3 remain
        vals = [r.summary["i"] for r in history]
        assert vals == [2, 3, 4]

    def test_job_names_returns_all_known(self):
        tracker = JobHistoryTracker()
        for name in ("x", "y", "z"):
            tracker.start_run(name)
        assert set(tracker.job_names()) == {"x", "y", "z"}

    def test_clear_removes_all_records(self):
        tracker = JobHistoryTracker()
        rec = tracker.start_run("job")
        tracker.finish_run(rec, status="ok")
        tracker.clear()
        assert tracker.all_last_runs() == []
        assert tracker.last_run("job") is None

    def test_run_history_empty_before_any_run(self):
        tracker = JobHistoryTracker()
        assert tracker.run_history("unknown_job") == []

    def test_duration_ms_non_negative(self):
        tracker = JobHistoryTracker()
        rec = tracker.start_run("timing_job")
        tracker.finish_run(rec, status="ok")
        assert rec.duration_ms >= 0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestGetJobHistoryTracker:
    def test_singleton_same_instance(self):
        t1 = get_job_history_tracker()
        t2 = get_job_history_tracker()
        assert t1 is t2

    def test_singleton_is_job_history_tracker(self):
        assert isinstance(get_job_history_tracker(), JobHistoryTracker)


# ---------------------------------------------------------------------------
# AST check — api.ts + settings page
# ---------------------------------------------------------------------------

class TestFrontendIntegration:
    def test_job_history_in_api_ts(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "lib" / "api.ts"
        if not src.exists():
            pytest.skip("api.ts tidak ditemukan")
        content = src.read_text()
        assert "JobRunRow" in content
        assert "JobHistoryStatus" in content
        assert "jobHistory" in content

    def test_scheduler_section_in_settings(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent.parent / "apps" / "web" / "app" / "settings" / "page.tsx"
        if not src.exists():
            pytest.skip("settings/page.tsx tidak ditemukan")
        content = src.read_text()
        assert "SchedulerJobsSection" in content
        assert "jobHistory" in content
        assert "StatusDot" in content
