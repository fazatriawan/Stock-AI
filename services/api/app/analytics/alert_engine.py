"""
R19 — Alert Engine.

Komponen:
1. AlertCondition — evaluasi apakah satu rule terpenuhi berdasarkan snapshot harga/teknikal
2. cooldown_ok     — cek apakah rule boleh fire lagi (belum dalam cooldown)
3. build_dedup_key — buat dedup key untuk tabel alerts
4. format_webhook_payload — serialize alert untuk POST ke webhook URL

Rule types yang didukung:
  price_above       — last_price > threshold
  price_below       — last_price < threshold
  pct_change_1d_above — return 1D > threshold (%)
  pct_change_1d_below — return 1D < threshold (%)
  rsi_above         — RSI-14 > threshold
  rsi_below         — RSI-14 < threshold
  swing_breakout    — setup type = BREAKOUT (tidak butuh threshold)
  swing_pullback    — setup type = PULLBACK (tidak butuh threshold)
  macro_inverted    — yield curve INVERTED (tidak butuh symbol)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Structs
# ---------------------------------------------------------------------------

@dataclass
class AlertEvalContext:
    """Data yang dibutuhkan untuk evaluasi satu rule."""
    symbol: Optional[str]
    last_price: Optional[float]
    return_1d: Optional[float]       # persen, mis. 3.5 = +3.5%
    rsi_14: Optional[float]
    swing_setup_type: Optional[str]  # BREAKOUT / PULLBACK / NO_SETUP / None
    yield_curve_signal: Optional[str]  # NORMAL / FLAT / INVERTED / None


@dataclass
class AlertFired:
    rule_id: str
    rule_type: str
    symbol: Optional[str]
    message: str
    value: Optional[float]
    threshold: Optional[float]
    fired_at: datetime


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def evaluate_rule(
    rule_id: str,
    rule_type: str,
    threshold: Optional[float],
    ctx: AlertEvalContext,
) -> Optional[AlertFired]:
    """
    Evaluasi satu rule. Return AlertFired jika kondisi terpenuhi, None jika tidak.
    Tidak melakukan cooldown check — itu tanggung jawab caller.
    """
    now = datetime.now(tz=timezone.utc)
    sym = ctx.symbol or "GLOBAL"

    if rule_type == "price_above":
        if ctx.last_price is not None and threshold is not None and ctx.last_price > threshold:
            return AlertFired(
                rule_id=rule_id, rule_type=rule_type, symbol=ctx.symbol,
                message=f"{sym}: harga {ctx.last_price:,.2f} melewati batas atas {threshold:,.2f}",
                value=ctx.last_price, threshold=threshold, fired_at=now,
            )

    elif rule_type == "price_below":
        if ctx.last_price is not None and threshold is not None and ctx.last_price < threshold:
            return AlertFired(
                rule_id=rule_id, rule_type=rule_type, symbol=ctx.symbol,
                message=f"{sym}: harga {ctx.last_price:,.2f} di bawah batas {threshold:,.2f}",
                value=ctx.last_price, threshold=threshold, fired_at=now,
            )

    elif rule_type == "pct_change_1d_above":
        if ctx.return_1d is not None and threshold is not None and ctx.return_1d > threshold:
            return AlertFired(
                rule_id=rule_id, rule_type=rule_type, symbol=ctx.symbol,
                message=f"{sym}: naik {ctx.return_1d:.2f}% dalam 1 hari (batas: +{threshold:.2f}%)",
                value=ctx.return_1d, threshold=threshold, fired_at=now,
            )

    elif rule_type == "pct_change_1d_below":
        if ctx.return_1d is not None and threshold is not None and ctx.return_1d < threshold:
            return AlertFired(
                rule_id=rule_id, rule_type=rule_type, symbol=ctx.symbol,
                message=f"{sym}: turun {ctx.return_1d:.2f}% dalam 1 hari (batas: {threshold:.2f}%)",
                value=ctx.return_1d, threshold=threshold, fired_at=now,
            )

    elif rule_type == "rsi_above":
        if ctx.rsi_14 is not None and threshold is not None and ctx.rsi_14 > threshold:
            return AlertFired(
                rule_id=rule_id, rule_type=rule_type, symbol=ctx.symbol,
                message=f"{sym}: RSI-14={ctx.rsi_14:.1f} melewati {threshold:.0f} (overbought)",
                value=ctx.rsi_14, threshold=threshold, fired_at=now,
            )

    elif rule_type == "rsi_below":
        if ctx.rsi_14 is not None and threshold is not None and ctx.rsi_14 < threshold:
            return AlertFired(
                rule_id=rule_id, rule_type=rule_type, symbol=ctx.symbol,
                message=f"{sym}: RSI-14={ctx.rsi_14:.1f} di bawah {threshold:.0f} (oversold)",
                value=ctx.rsi_14, threshold=threshold, fired_at=now,
            )

    elif rule_type == "swing_breakout":
        if ctx.swing_setup_type == "BREAKOUT":
            return AlertFired(
                rule_id=rule_id, rule_type=rule_type, symbol=ctx.symbol,
                message=f"{sym}: terdeteksi setup BREAKOUT",
                value=None, threshold=None, fired_at=now,
            )

    elif rule_type == "swing_pullback":
        if ctx.swing_setup_type == "PULLBACK":
            return AlertFired(
                rule_id=rule_id, rule_type=rule_type, symbol=ctx.symbol,
                message=f"{sym}: terdeteksi setup PULLBACK",
                value=None, threshold=None, fired_at=now,
            )

    elif rule_type == "macro_inverted":
        if ctx.yield_curve_signal == "INVERTED":
            return AlertFired(
                rule_id=rule_id, rule_type=rule_type, symbol=None,
                message="Yield curve US TERBALIK — sinyal historis resesi",
                value=None, threshold=None, fired_at=now,
            )

    return None


# ---------------------------------------------------------------------------
# Cooldown check
# ---------------------------------------------------------------------------

def cooldown_ok(last_fired_at: Optional[datetime], cooldown_hours: int) -> bool:
    """True jika rule boleh fire (belum dalam cooldown atau belum pernah fire)."""
    if last_fired_at is None:
        return True
    if last_fired_at.tzinfo is None:
        last_fired_at = last_fired_at.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(tz=timezone.utc) - last_fired_at
    return elapsed >= timedelta(hours=cooldown_hours)


# ---------------------------------------------------------------------------
# Dedup key
# ---------------------------------------------------------------------------

def build_dedup_key(rule_id: str, fired_at: datetime) -> str:
    """
    Dedup key = hash(rule_id + date window).
    Window = tanggal UTC dari fired_at → satu alert per rule per hari.
    """
    day_str = fired_at.strftime("%Y-%m-%d")
    raw = f"{rule_id}:{day_str}"
    return hashlib.sha1(raw.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Webhook payload builder
# ---------------------------------------------------------------------------

def build_webhook_payload(fired: AlertFired) -> dict:
    """Payload JSON untuk dikirim ke webhook. Format kompatibel Slack incoming webhook."""
    return {
        "text": fired.message,
        "attachments": [
            {
                "color": "#ff9900" if "INVERTED" in fired.message or "turun" in fired.message else "#36a64f",
                "fields": [
                    {"title": "Rule", "value": fired.rule_type, "short": True},
                    {"title": "Symbol", "value": fired.symbol or "GLOBAL", "short": True},
                    {"title": "Nilai", "value": str(round(fired.value, 4)) if fired.value is not None else "—", "short": True},
                    {"title": "Waktu", "value": fired.fired_at.isoformat(), "short": True},
                ],
                "footer": "Stock Intelligence Alert",
            }
        ],
    }
