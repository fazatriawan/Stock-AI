"""
FREE-21 — Platform health summary.

Mengagregasi empat sinyal menjadi satu skor 0-100:
  1. Freshness  (40 poin) — % bar FRESH dari total price_bars
  2. Gaps       (25 poin) — penalti berdasarkan instrumen dengan gap CRITICAL/WARNING
  3. Quota      (20 poin) — penalti jika ada provider quota exhausted
  4. Jobs       (15 poin) — penalti berdasarkan error job scheduler terakhir

Tidak menyentuh provider eksternal — hanya baca DB + in-process state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.gap_detector import detect_data_gaps
from app.providers.quota_tracker import get_quota_tracker
from app.scheduling.job_history import get_job_history_tracker


@dataclass
class FreshnessHealth:
    total_bars: int
    fresh_bars: int
    stale_bars: int
    fresh_pct: float
    score: int  # 0-40


@dataclass
class GapsHealth:
    critical_count: int
    warning_count: int
    score: int  # 0-25


@dataclass
class QuotaHealth:
    exhausted_providers: list[str]
    score: int  # 0-20


@dataclass
class JobsHealth:
    total_known: int
    error_count: int
    last_error_job: Optional[str]
    score: int  # 0-15


@dataclass
class PlatformHealthResult:
    overall_score: int          # 0-100
    grade: str                  # A/B/C/D/F
    freshness: FreshnessHealth
    gaps: GapsHealth
    quota: QuotaHealth
    jobs: JobsHealth
    computed_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 55:
        return "C"
    if score >= 35:
        return "D"
    return "F"


async def compute_platform_health(db: AsyncSession) -> PlatformHealthResult:
    # ------------------------------------------------------------------ #
    # 1. Freshness (40 pts)
    # ------------------------------------------------------------------ #
    row = await db.execute(
        text(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN freshness_status = 'FRESH' THEN 1 ELSE 0 END) AS fresh "
            "FROM price_bars"
        )
    )
    r = row.one()
    total_bars = int(r.total or 0)
    fresh_bars = int(r.fresh or 0)
    stale_bars = total_bars - fresh_bars
    fresh_pct = round((fresh_bars / total_bars * 100) if total_bars > 0 else 100.0, 1)
    # Linear: 100% fresh → 40pts, 50% fresh → 20pts, 0% → 0pts
    freshness_score = round(fresh_pct / 100 * 40)
    freshness_health = FreshnessHealth(
        total_bars=total_bars,
        fresh_bars=fresh_bars,
        stale_bars=stale_bars,
        fresh_pct=fresh_pct,
        score=freshness_score,
    )

    # ------------------------------------------------------------------ #
    # 2. Gaps (25 pts)
    # ------------------------------------------------------------------ #
    gap_result = await detect_data_gaps(db, threshold_pct=10.0, min_days_history=30, limit=200)
    critical_count = sum(1 for r2 in gap_result.reports if r2.severity == "CRITICAL")
    warning_count = sum(1 for r2 in gap_result.reports if r2.severity == "WARNING")
    # Deductions: each CRITICAL -5, each WARNING -2, min 0
    gap_deduction = min(25, critical_count * 5 + warning_count * 2)
    gap_score = max(0, 25 - gap_deduction)
    gaps_health = GapsHealth(
        critical_count=critical_count,
        warning_count=warning_count,
        score=gap_score,
    )

    # ------------------------------------------------------------------ #
    # 3. Quota (20 pts)
    # ------------------------------------------------------------------ #
    tracker = get_quota_tracker()
    exhausted = [s.provider_name for s in tracker.all_stats() if s.quota_exhausted]
    # Any exhausted provider → half points; 0 exhausted → full 20
    quota_score = 10 if exhausted else 20
    quota_health = QuotaHealth(exhausted_providers=exhausted, score=quota_score)

    # ------------------------------------------------------------------ #
    # 4. Jobs (15 pts)
    # ------------------------------------------------------------------ #
    jtracker = get_job_history_tracker()
    last_runs = jtracker.all_last_runs()
    error_jobs = [rec for rec in last_runs if rec.status == "error"]
    last_error_job = error_jobs[0].job_name if error_jobs else None
    # Each errored job -5pts, min 0
    job_deduction = min(15, len(error_jobs) * 5)
    job_score = max(0, 15 - job_deduction)
    jobs_health = JobsHealth(
        total_known=len(last_runs),
        error_count=len(error_jobs),
        last_error_job=last_error_job,
        score=job_score,
    )

    overall = freshness_score + gap_score + quota_score + job_score

    return PlatformHealthResult(
        overall_score=overall,
        grade=_grade(overall),
        freshness=freshness_health,
        gaps=gaps_health,
        quota=quota_health,
        jobs=jobs_health,
    )
