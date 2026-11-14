"""
FREE-20 — Scheduler job history tracker (in-process, keamanan R0).

Menyimpan maksimum N run terakhir per job_name.
Singleton via get_job_history_tracker().
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class JobRunRecord:
    job_name: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str = "running"   # "running" | "ok" | "error"
    duration_ms: Optional[int] = None
    summary: dict = field(default_factory=dict)
    error: Optional[str] = None


class JobHistoryTracker:
    """Thread-safe ring buffer of job run records per job name."""

    def __init__(self, max_per_job: int = 20) -> None:
        self._lock = threading.Lock()
        self._max = max_per_job
        self._runs: dict[str, deque[JobRunRecord]] = {}

    def start_run(self, job_name: str) -> JobRunRecord:
        record = JobRunRecord(
            job_name=job_name,
            started_at=datetime.now(tz=timezone.utc),
        )
        with self._lock:
            if job_name not in self._runs:
                self._runs[job_name] = deque(maxlen=self._max)
            self._runs[job_name].append(record)
        return record

    def finish_run(
        self,
        record: JobRunRecord,
        status: str = "ok",
        summary: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        finished = datetime.now(tz=timezone.utc)
        duration = int((finished - record.started_at).total_seconds() * 1000)
        with self._lock:
            record.finished_at = finished
            record.status = status
            record.duration_ms = duration
            record.summary = summary or {}
            record.error = error

    def last_run(self, job_name: str) -> Optional[JobRunRecord]:
        with self._lock:
            buf = self._runs.get(job_name)
            if not buf:
                return None
            return buf[-1]

    def all_last_runs(self) -> list[JobRunRecord]:
        """Satu record terakhir per job, diurutkan berdasarkan started_at desc."""
        with self._lock:
            records = []
            for buf in self._runs.values():
                if buf:
                    records.append(buf[-1])
        records.sort(key=lambda r: r.started_at, reverse=True)
        return records

    def job_names(self) -> list[str]:
        with self._lock:
            return list(self._runs.keys())

    def run_history(self, job_name: str) -> list[JobRunRecord]:
        with self._lock:
            buf = self._runs.get(job_name)
            return list(buf) if buf else []

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


_tracker: Optional[JobHistoryTracker] = None
_tracker_lock = threading.Lock()


def get_job_history_tracker() -> JobHistoryTracker:
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = JobHistoryTracker()
    return _tracker
