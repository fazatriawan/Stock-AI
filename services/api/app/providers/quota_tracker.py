"""
FREE-15: Per-provider daily call counter.

Mencegah pemborosan retry ke provider yang sudah mencapai batas harian.
In-process counter — reset otomatis saat tanggal berubah, tanpa Redis/DB.

Prinsip:
- Hanya menghitung panggilan OHLCV outbound (bukan health probe).
- Jika provider tidak mendeclare quota_per_day, counter tetap berjalan
  tapi tidak pernah memblokir (quota dianggap tak terbatas).
- Thread-safe dengan threading.Lock — aman untuk APScheduler + FastAPI worker.
- TIDAK pernah mencatat data harga atau konten respons.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from typing import Optional

import structlog

from app.providers.base import ProviderCapability

log = structlog.get_logger(__name__)


@dataclass
class ProviderCallStats:
    """Statistik panggilan hari ini untuk satu provider."""
    provider_name: str
    calls_today: int
    quota_per_day: Optional[int]
    quota_exhausted: bool
    date_str: str  # YYYY-MM-DD agar UI bisa tahu ini untuk hari apa


class ProviderQuotaTracker:
    """
    Singleton in-process tracker untuk daily call counts per provider.

    Usage:
        tracker = get_quota_tracker()
        tracker.record_call("yfinance")
        if tracker.is_quota_exhausted("yfinance", capability):
            # skip provider
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}   # key: "provider_name"
        self._date: date = date.today()

    def _maybe_reset(self) -> None:
        """Reset counter jika tanggal sudah berubah (dipanggil di dalam lock)."""
        today = date.today()
        if today != self._date:
            self._counts = {}
            self._date = today
            log.info("quota_tracker.daily_reset", date=today.isoformat())

    def record_call(self, provider_name: str) -> int:
        """
        Catat satu panggilan outbound untuk provider. Kembalikan total hari ini.
        """
        with self._lock:
            self._maybe_reset()
            self._counts[provider_name] = self._counts.get(provider_name, 0) + 1
            count = self._counts[provider_name]
        log.debug("quota_tracker.call_recorded", provider=provider_name, calls_today=count)
        return count

    def get_calls_today(self, provider_name: str) -> int:
        with self._lock:
            self._maybe_reset()
            return self._counts.get(provider_name, 0)

    def is_quota_exhausted(
        self,
        provider_name: str,
        capability: Optional[ProviderCapability],
    ) -> bool:
        """
        True jika provider sudah melebihi quota_per_day-nya hari ini.
        False jika quota_per_day tidak dideklarasikan (tak terbatas).
        """
        if capability is None or capability.quota_per_day is None:
            return False
        calls = self.get_calls_today(provider_name)
        exhausted = calls >= capability.quota_per_day
        if exhausted:
            log.warning(
                "quota_tracker.exhausted",
                provider=provider_name,
                calls_today=calls,
                quota_per_day=capability.quota_per_day,
            )
        return exhausted

    def all_stats(self) -> list[ProviderCallStats]:
        """Kembalikan stats semua provider yang tercatat hari ini."""
        with self._lock:
            self._maybe_reset()
            today_str = self._date.isoformat()
            return [
                ProviderCallStats(
                    provider_name=name,
                    calls_today=count,
                    quota_per_day=None,   # diisi oleh caller jika diketahui
                    quota_exhausted=False,  # diisi oleh caller
                    date_str=today_str,
                )
                for name, count in self._counts.items()
            ]

    def reset_provider(self, provider_name: str) -> None:
        """Reset counter satu provider (manual / test)."""
        with self._lock:
            self._counts.pop(provider_name, None)

    def reset_all(self) -> None:
        """Reset semua counter (manual / test)."""
        with self._lock:
            self._counts = {}


_tracker: Optional[ProviderQuotaTracker] = None


def get_quota_tracker() -> ProviderQuotaTracker:
    global _tracker
    if _tracker is None:
        _tracker = ProviderQuotaTracker()
    return _tracker
