"""
Circuit breaker per provider — R13.

State machine: CLOSED → OPEN → HALF_OPEN → CLOSED
  CLOSED:    request normal; hitung consecutive errors
  OPEN:      semua request ditolak tanpa mencoba provider
  HALF_OPEN: satu request percobaan; jika sukses → CLOSED, jika gagal → OPEN

Parameter:
  failure_threshold: berapa consecutive errors sebelum buka (default 5)
  recovery_timeout:  detik sebelum OPEN → HALF_OPEN (default 60)
  half_open_max:     berapa percobaan di HALF_OPEN sebelum keputusan (default 1)

Thread-safe untuk asyncio (single-thread) — tidak butuh lock.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CBState(str, Enum):
    CLOSED = "CLOSED"       # normal
    OPEN = "OPEN"           # menolak semua
    HALF_OPEN = "HALF_OPEN" # satu percobaan


@dataclass
class CircuitBreakerState:
    provider_name: str
    state: CBState = CBState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_at: Optional[float] = None   # time.monotonic()
    last_success_at: Optional[float] = None
    last_error: Optional[str] = None
    opened_at: Optional[float] = None
    total_calls: int = 0
    total_rejections: int = 0


class CircuitBreaker:
    """
    Circuit breaker ringan untuk setiap provider.
    Tidak ada I/O — hanya state machine di memori.
    """

    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.provider_name = provider_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitBreakerState(provider_name=provider_name)

    @property
    def state(self) -> CBState:
        self._maybe_transition_to_half_open()
        return self._state.state

    def _maybe_transition_to_half_open(self) -> None:
        if (
            self._state.state == CBState.OPEN
            and self._state.opened_at is not None
            and (time.monotonic() - self._state.opened_at) >= self.recovery_timeout
        ):
            self._state.state = CBState.HALF_OPEN
            self._state.success_count = 0

    def allow_request(self) -> bool:
        """Apakah request boleh diteruskan ke provider?"""
        s = self.state
        self._state.total_calls += 1
        if s == CBState.CLOSED:
            return True
        if s == CBState.HALF_OPEN:
            return True
        # OPEN
        self._state.total_rejections += 1
        return False

    def record_success(self) -> None:
        """Panggil ini setelah provider berhasil."""
        self._state.last_success_at = time.monotonic()
        self._state.last_error = None

        if self._state.state == CBState.HALF_OPEN:
            # Recovery berhasil → CLOSED
            self._state.state = CBState.CLOSED
            self._state.failure_count = 0
            self._state.opened_at = None
        elif self._state.state == CBState.CLOSED:
            self._state.failure_count = 0

    def record_failure(self, error: str = "") -> None:
        """Panggil ini setelah provider gagal."""
        self._state.failure_count += 1
        self._state.last_failure_at = time.monotonic()
        self._state.last_error = error[:200]  # potong pesan panjang

        if self._state.state in (CBState.CLOSED, CBState.HALF_OPEN):
            if self._state.failure_count >= self.failure_threshold:
                self._state.state = CBState.OPEN
                self._state.opened_at = time.monotonic()

    def get_status(self) -> dict:
        return {
            "provider": self.provider_name,
            "state": self.state.value,
            "failure_count": self._state.failure_count,
            "last_error": self._state.last_error,
            "last_success_at": self._state.last_success_at,
            "total_calls": self._state.total_calls,
            "total_rejections": self._state.total_rejections,
        }


# ---------------------------------------------------------------------------
# Singleton registry of circuit breakers
# ---------------------------------------------------------------------------

_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(provider_name: str) -> CircuitBreaker:
    if provider_name not in _breakers:
        _breakers[provider_name] = CircuitBreaker(provider_name)
    return _breakers[provider_name]


def all_circuit_breaker_statuses() -> list[dict]:
    return [cb.get_status() for cb in _breakers.values()]
