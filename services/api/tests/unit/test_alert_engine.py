"""Unit tests untuk R19 Alert Engine."""
import pytest
from datetime import datetime, timedelta, timezone

from app.analytics.alert_engine import (
    AlertEvalContext,
    build_dedup_key,
    build_webhook_payload,
    cooldown_ok,
    evaluate_rule,
)


def _ctx(**kwargs) -> AlertEvalContext:
    defaults = dict(
        symbol="BBCA",
        last_price=10_000.0,
        return_1d=0.0,
        rsi_14=50.0,
        swing_setup_type=None,
        yield_curve_signal="NORMAL",
    )
    defaults.update(kwargs)
    return AlertEvalContext(**defaults)


# ---------------------------------------------------------------------------
# price_above
# ---------------------------------------------------------------------------

def test_price_above_fires_when_exceeded():
    ctx = _ctx(last_price=10_500.0)
    fired = evaluate_rule("r1", "price_above", 10_000.0, ctx)
    assert fired is not None
    assert fired.rule_type == "price_above"
    assert fired.value == 10_500.0


def test_price_above_no_fire_below():
    ctx = _ctx(last_price=9_900.0)
    fired = evaluate_rule("r1", "price_above", 10_000.0, ctx)
    assert fired is None


# ---------------------------------------------------------------------------
# price_below
# ---------------------------------------------------------------------------

def test_price_below_fires():
    ctx = _ctx(last_price=8_000.0)
    fired = evaluate_rule("r1", "price_below", 9_000.0, ctx)
    assert fired is not None
    assert fired.value == 8_000.0


def test_price_below_no_fire_above():
    ctx = _ctx(last_price=10_000.0)
    fired = evaluate_rule("r1", "price_below", 9_000.0, ctx)
    assert fired is None


# ---------------------------------------------------------------------------
# pct_change_1d
# ---------------------------------------------------------------------------

def test_pct_change_1d_above_fires():
    ctx = _ctx(return_1d=6.5)
    fired = evaluate_rule("r1", "pct_change_1d_above", 5.0, ctx)
    assert fired is not None
    assert fired.value == pytest.approx(6.5)


def test_pct_change_1d_below_fires():
    ctx = _ctx(return_1d=-4.0)
    fired = evaluate_rule("r1", "pct_change_1d_below", -3.0, ctx)
    assert fired is not None


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def test_rsi_above_fires():
    ctx = _ctx(rsi_14=75.0)
    fired = evaluate_rule("r1", "rsi_above", 70.0, ctx)
    assert fired is not None
    assert "overbought" in fired.message


def test_rsi_below_fires():
    ctx = _ctx(rsi_14=25.0)
    fired = evaluate_rule("r1", "rsi_below", 30.0, ctx)
    assert fired is not None
    assert "oversold" in fired.message


# ---------------------------------------------------------------------------
# Swing setup
# ---------------------------------------------------------------------------

def test_swing_breakout_fires():
    ctx = _ctx(swing_setup_type="BREAKOUT")
    fired = evaluate_rule("r1", "swing_breakout", None, ctx)
    assert fired is not None
    assert "BREAKOUT" in fired.message


def test_swing_pullback_fires():
    ctx = _ctx(swing_setup_type="PULLBACK")
    fired = evaluate_rule("r1", "swing_pullback", None, ctx)
    assert fired is not None


def test_swing_breakout_no_fire_on_no_setup():
    ctx = _ctx(swing_setup_type=None)
    fired = evaluate_rule("r1", "swing_breakout", None, ctx)
    assert fired is None


# ---------------------------------------------------------------------------
# Macro inverted
# ---------------------------------------------------------------------------

def test_macro_inverted_fires():
    ctx = _ctx(yield_curve_signal="INVERTED")
    fired = evaluate_rule("r1", "macro_inverted", None, ctx)
    assert fired is not None
    assert "resesi" in fired.message.lower() or "INVERTED" in fired.message


def test_macro_inverted_no_fire_normal():
    ctx = _ctx(yield_curve_signal="NORMAL")
    fired = evaluate_rule("r1", "macro_inverted", None, ctx)
    assert fired is None


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def test_cooldown_ok_never_fired():
    assert cooldown_ok(None, 24) is True


def test_cooldown_ok_after_cooldown():
    past = datetime.now(tz=timezone.utc) - timedelta(hours=25)
    assert cooldown_ok(past, 24) is True


def test_cooldown_blocked_within_period():
    recent = datetime.now(tz=timezone.utc) - timedelta(hours=2)
    assert cooldown_ok(recent, 24) is False


def test_cooldown_exact_boundary():
    exact = datetime.now(tz=timezone.utc) - timedelta(hours=24, seconds=1)
    assert cooldown_ok(exact, 24) is True


# ---------------------------------------------------------------------------
# Dedup key
# ---------------------------------------------------------------------------

def test_dedup_key_same_day_same():
    t1 = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 4, 20, 0, tzinfo=timezone.utc)
    assert build_dedup_key("rule-x", t1) == build_dedup_key("rule-x", t2)


def test_dedup_key_different_day_different():
    t1 = datetime(2026, 11, 4, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 5, tzinfo=timezone.utc)
    assert build_dedup_key("rule-x", t1) != build_dedup_key("rule-x", t2)


def test_dedup_key_different_rule_different():
    t = datetime(2026, 11, 4, tzinfo=timezone.utc)
    assert build_dedup_key("rule-a", t) != build_dedup_key("rule-b", t)


# ---------------------------------------------------------------------------
# Webhook payload
# ---------------------------------------------------------------------------

def test_webhook_payload_has_required_fields():
    ctx = _ctx(last_price=10_500.0)
    fired = evaluate_rule("r1", "price_above", 10_000.0, ctx)
    assert fired is not None
    payload = build_webhook_payload(fired)
    assert "text" in payload
    assert "attachments" in payload
    assert len(payload["attachments"]) > 0
