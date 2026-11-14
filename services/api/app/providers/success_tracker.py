"""
FREE-26: Per-provider daily success/failure tracker.

Melengkapi ProviderQuotaTracker (jumlah panggilan) dengan info
apakah panggilan itu berhasil (bars dikembalikan) atau gagal (exception).
In-process, thread-safe, reset harian otomatis.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import structlog

log = structlog.get_logger(__name__)


@dataclass
class ProviderSuccessStats:
    """Statistik sukses/gagal hari ini untuk satu provider."""
    provider_name: str
    date_str: str
    calls_succeeded: int = 0
    calls_failed: int = 0
    bars_fetched: int = 0
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_error: Optional[str] = None

    @property
    def total_calls(self) -> int:
        return self.calls_succeeded + self.calls_failed

    @property
    def success_rate(self) -> float:
        total = self.total_calls
        if total == 0:
            return 0.0
        return round(self.calls_succeeded / total * 100, 1)


class ProviderSuccessTracker:
    """
    Singleton in-process tracker untuk daily success/failure per provider.

    Usage:
        tracker = get_success_tracker()
        tracker.record_success("yfinance", bars=120)
        tracker.record_failure("sectors", error="Connection timeout")
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: dict[str, ProviderSuccessStats] = {}
        self._date: date = date.today()

    def _maybe_reset(self) -> None:
        today = date.today()
        if today != self._date:
            self._stats = {}
            self._date = today
            log.info("success_tracker.daily_reset", date=today.isoformat())

    def _get_or_create(self, provider_name: str) -> ProviderSuccessStats:
        if provider_name not in self._stats:
            self._stats[provider_name] = ProviderSuccessStats(
                provider_name=provider_name,
                date_str=self._date.isoformat(),
            )
        return self._stats[provider_name]

    def record_success(self, provider_name: str, bars: int = 0) -> None:
        with self._lock:
            self._maybe_reset()
            s = self._get_or_create(provider_name)
            s.calls_succeeded += 1
            s.bars_fetched += bars
            s.last_success_at = datetime.now(tz=timezone.utc)
        log.debug(
            "success_tracker.success",
            provider=provider_name,
            bars=bars,
            total_succeeded=self._stats[provider_name].calls_succeeded,
        )

    def record_failure(self, provider_name: str, error: str = "") -> None:
        with self._lock:
            self._maybe_reset()
            s = self._get_or_create(provider_name)
            s.calls_failed += 1
            s.last_failure_at = datetime.now(tz=timezone.utc)
            if error:
                s.last_error = error[:256]  # truncate panjang stack trace
        log.debug(
            "success_tracker.failure",
            provider=provider_name,
            error=error[:100] if error else "",
            total_failed=self._stats[provider_name].calls_failed,
        )

    def get_stats(self, provider_name: str) -> Optional[ProviderSuccessStats]:
        with self._lock:
            self._maybe_reset()
            return self._stats.get(provider_name)

    def all_stats(self) -> list[ProviderSuccessStats]:
        with self._lock:
            self._maybe_reset()
            return sorted(
                self._stats.values(),
                key=lambda s: s.total_calls,
                reverse=True,
            )

    def reset_all(self) -> None:
        with self._lock:
            self._stats = {}


_tracker: Optional[ProviderSuccessTracker] = None


def get_success_tracker() -> ProviderSuccessTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProviderSuccessTracker()
    return _tracker
