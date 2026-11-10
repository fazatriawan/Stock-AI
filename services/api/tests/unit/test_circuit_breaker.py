"""Unit tests untuk Circuit Breaker (R13)."""
import time

from app.providers.circuit_breaker import (
    CBState,
    CircuitBreaker,
    get_circuit_breaker,
    _breakers,
)


def _fresh(name="test_provider", threshold=3, timeout=60.0) -> CircuitBreaker:
    return CircuitBreaker(name, failure_threshold=threshold, recovery_timeout=timeout)


# ---------------------------------------------------------------------------
# CLOSED state
# ---------------------------------------------------------------------------

def test_initial_state_closed():
    cb = _fresh()
    assert cb.state == CBState.CLOSED

def test_allows_request_when_closed():
    cb = _fresh()
    assert cb.allow_request() is True

def test_success_resets_failure_count():
    cb = _fresh()
    cb.record_failure("err1")
    cb.record_failure("err2")
    cb.record_success()
    assert cb._state.failure_count == 0
    assert cb.state == CBState.CLOSED


# ---------------------------------------------------------------------------
# OPEN state
# ---------------------------------------------------------------------------

def test_opens_after_threshold_failures():
    cb = _fresh(threshold=3)
    cb.record_failure("e1")
    cb.record_failure("e2")
    assert cb.state == CBState.CLOSED  # belum buka
    cb.record_failure("e3")
    assert cb.state == CBState.OPEN

def test_rejects_request_when_open():
    cb = _fresh(threshold=2)
    cb.record_failure("e1")
    cb.record_failure("e2")
    assert cb.allow_request() is False

def test_tracks_rejections():
    cb = _fresh(threshold=1)
    cb.record_failure("e1")
    cb.allow_request()  # rejected
    cb.allow_request()  # rejected
    assert cb._state.total_rejections == 2


# ---------------------------------------------------------------------------
# HALF_OPEN state
# ---------------------------------------------------------------------------

def test_transitions_to_half_open_after_timeout():
    cb = _fresh(threshold=2, timeout=0.01)  # 10ms timeout
    cb.record_failure("e1")
    cb.record_failure("e2")
    assert cb.state == CBState.OPEN
    time.sleep(0.02)
    assert cb.state == CBState.HALF_OPEN

def test_half_open_success_closes():
    cb = _fresh(threshold=2, timeout=0.01)
    cb.record_failure("e1")
    cb.record_failure("e2")
    time.sleep(0.02)
    assert cb.state == CBState.HALF_OPEN
    cb.record_success()
    assert cb.state == CBState.CLOSED

def test_half_open_failure_reopens():
    cb = _fresh(threshold=2, timeout=0.01)
    cb.record_failure("e1")
    cb.record_failure("e2")
    time.sleep(0.02)
    assert cb.state == CBState.HALF_OPEN
    cb.record_failure("e3")  # satu kali gagal lagi saat HALF_OPEN
    assert cb.state == CBState.OPEN


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

def test_get_status_returns_dict():
    cb = _fresh("my_provider")
    cb.record_failure("connection refused")
    status = cb.get_status()
    assert status["provider"] == "my_provider"
    assert status["state"] == CBState.CLOSED.value  # belum threshold
    assert status["failure_count"] == 1
    assert status["last_error"] == "connection refused"


# ---------------------------------------------------------------------------
# Singleton registry
# ---------------------------------------------------------------------------

def test_get_circuit_breaker_returns_same_instance():
    # Bersihkan dulu
    _breakers.pop("singleton_test", None)
    cb1 = get_circuit_breaker("singleton_test")
    cb2 = get_circuit_breaker("singleton_test")
    assert cb1 is cb2
    _breakers.pop("singleton_test", None)


# ---------------------------------------------------------------------------
# Ops monitor backup status
# ---------------------------------------------------------------------------

def test_backup_status_never(tmp_path):
    from app.domain.ops_monitor import get_backup_status
    import app.domain.ops_monitor as om
    # Override sentinel path
    original = om.BACKUP_SENTINEL_PATH
    om.BACKUP_SENTINEL_PATH = tmp_path / ".last_backup"
    result = get_backup_status()
    om.BACKUP_SENTINEL_PATH = original
    assert result["status"] == "NEVER"

def test_backup_status_ok(tmp_path):
    from datetime import datetime, timezone
    import app.domain.ops_monitor as om
    original = om.BACKUP_SENTINEL_PATH
    sentinel = tmp_path / ".last_backup"
    sentinel.write_text(datetime.now(tz=timezone.utc).isoformat())
    om.BACKUP_SENTINEL_PATH = sentinel
    result = get_backup_status()
    om.BACKUP_SENTINEL_PATH = original
    assert result["status"] == "OK"
    assert result["age_hours"] < 1


from app.domain.ops_monitor import get_backup_status  # noqa: E402
