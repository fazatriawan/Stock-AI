"""
R19 — Alert & Notification Engine routes.

GET    /alerts/rules           → Daftar semua alert rules aktif
POST   /alerts/rules           → Buat alert rule baru
DELETE /alerts/rules/{id}      → Hapus / nonaktifkan rule
POST   /alerts/evaluate        → Evaluasi semua rules sekarang, kirim webhook jika ada yang fire
GET    /alerts/history         → Riwayat alert yang sudah fired (dari tabel alerts)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.alert_engine import (
    AlertEvalContext,
    build_dedup_key,
    build_webhook_payload,
    cooldown_ok,
    evaluate_rule,
)
from app.analytics.swing import SetupType, detect_swing_setup
from app.analytics.technical import compute_technical_snapshot
from app.api.schemas import (
    AlertEvalResponse,
    AlertFiredResponse,
    AlertRuleCreateRequest,
    AlertRuleResponse,
)
from app.db.base import new_uuid
from app.db.models import Alert, AlertRule, Instrument, PriceBar
from app.db.session import get_db

import pandas as pd
from datetime import date, timedelta

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])

_PRICE_DAYS = 60


async def _load_price_df(instrument_id: str, db: AsyncSession) -> pd.DataFrame:
    end   = date.today()
    start = end - timedelta(days=_PRICE_DAYS)
    result = await db.execute(
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument_id,
               PriceBar.session_date.between(start, end))
        .order_by(PriceBar.session_date.asc())
    )
    bars = result.scalars().all()
    if not bars:
        return pd.DataFrame()
    return pd.DataFrame([{
        "session_date": b.session_date,
        "open":   float(b.open)  if b.open  else None,
        "high":   float(b.high)  if b.high  else float(b.close),
        "low":    float(b.low)   if b.low   else float(b.close),
        "close":  float(b.close),
        "volume": b.volume or 0,
    } for b in bars])


# ---------------------------------------------------------------------------
# CRUD Rules
# ---------------------------------------------------------------------------

@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> list[AlertRuleResponse]:
    """Daftar alert rules, default hanya yang aktif."""
    query = select(AlertRule).order_by(AlertRule.created_at.desc())
    if active_only:
        query = query.where(AlertRule.is_active == True)  # noqa: E712
    result = await db.execute(query)
    rules = result.scalars().all()
    return [AlertRuleResponse.model_validate(r) for r in rules]


@router.post("/rules", response_model=AlertRuleResponse, status_code=201)
async def create_alert_rule(
    body: AlertRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> AlertRuleResponse:
    """
    Buat alert rule baru.

    Rule types:
    - **price_above/below**: threshold_value = harga dalam currency instrumen
    - **pct_change_1d_above/below**: threshold_value = % (mis. 5.0 = +5%)
    - **rsi_above/below**: threshold_value = nilai RSI (0–100)
    - **swing_breakout/pullback**: tidak butuh threshold, hanya canonical_symbol
    - **macro_inverted**: tidak butuh symbol atau threshold (yield curve global)

    webhook_url opsional — jika diisi, payload JSON akan di-POST saat alert fire.
    """
    # Validasi: rule yang butuh symbol
    needs_symbol = body.rule_type not in ("macro_inverted",)
    if needs_symbol and not body.canonical_symbol:
        raise HTTPException(status_code=422, detail=f"rule_type '{body.rule_type}' membutuhkan canonical_symbol")

    # Validasi: rule yang butuh threshold
    needs_threshold = body.rule_type in (
        "price_above", "price_below",
        "pct_change_1d_above", "pct_change_1d_below",
        "rsi_above", "rsi_below",
    )
    if needs_threshold and body.threshold_value is None:
        raise HTTPException(status_code=422, detail=f"rule_type '{body.rule_type}' membutuhkan threshold_value")

    rule = AlertRule(
        id=new_uuid(),
        rule_type=body.rule_type,
        canonical_symbol=body.canonical_symbol.upper() if body.canonical_symbol else None,
        threshold_value=body.threshold_value,
        cooldown_hours=body.cooldown_hours,
        is_active=True,
        fire_count=0,
        webhook_url=body.webhook_url,
        notes=body.notes,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    log.info("alert_rule.created", id=rule.id, type=rule.rule_type, symbol=rule.canonical_symbol)
    return AlertRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=204, response_model=None)
async def delete_alert_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Nonaktifkan rule (soft delete — is_active = False)."""
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule tidak ditemukan")
    rule.is_active = False
    await db.commit()
    log.info("alert_rule.deactivated", id=rule_id)


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------

@router.post("/evaluate", response_model=AlertEvalResponse)
async def evaluate_alerts(db: AsyncSession = Depends(get_db)) -> AlertEvalResponse:
    """
    Evaluasi semua rules aktif sekarang.

    Untuk tiap rule:
    1. Ambil data terkini (harga, RSI, swing setup)
    2. Evaluasi kondisi rule
    3. Cek cooldown
    4. Jika fire: simpan ke tabel alerts + kirim webhook (jika ada URL)

    Endpoint ini aman dipanggil berulang kali — cooldown mencegah spam.
    """
    result = await db.execute(
        select(AlertRule).where(AlertRule.is_active == True)  # noqa: E712
    )
    rules = result.scalars().all()

    # Ambil yield curve signal (untuk macro_inverted rule)
    yc_result = await db.execute(text("""
        SELECT series_id, value FROM macro_observations
        WHERE series_id IN ('TREASURY_10Y', 'TREASURY_2Y', 'YIELD_10Y_2Y')
        ORDER BY observed_date DESC
        LIMIT 6
    """))
    yc_rows = {row[0]: float(row[1]) for row in yc_result if row[1] is not None}
    t10 = yc_rows.get("TREASURY_10Y")
    t2  = yc_rows.get("TREASURY_2Y")
    spread = yc_rows.get("YIELD_10Y_2Y")
    if t10 is not None and t2 is not None:
        yc_signal = "INVERTED" if (t10 - t2) < 0 else ("FLAT" if (t10 - t2) < 0.5 else "NORMAL")
    elif spread is not None:
        yc_signal = "INVERTED" if spread < 0 else ("FLAT" if spread < 0.5 else "NORMAL")
    else:
        yc_signal = None

    # Cache data per symbol agar tidak fetch ulang untuk banyak rules
    ctx_cache: dict[str, AlertEvalContext] = {}

    async def _get_ctx(symbol: Optional[str]) -> AlertEvalContext:
        if symbol is None:
            return AlertEvalContext(
                symbol=None, last_price=None, return_1d=None,
                rsi_14=None, swing_setup_type=None, yield_curve_signal=yc_signal,
            )
        if symbol in ctx_cache:
            return ctx_cache[symbol]

        instr_res = await db.execute(
            select(Instrument).where(Instrument.canonical_symbol == symbol, Instrument.status == "ACTIVE")
        )
        instr = instr_res.scalar_one_or_none()
        if instr is None:
            ctx = AlertEvalContext(
                symbol=symbol, last_price=None, return_1d=None,
                rsi_14=None, swing_setup_type=None, yield_curve_signal=yc_signal,
            )
            ctx_cache[symbol] = ctx
            return ctx

        df = await _load_price_df(instr.id, db)
        if df.empty:
            ctx = AlertEvalContext(
                symbol=symbol, last_price=None, return_1d=None,
                rsi_14=None, swing_setup_type=None, yield_curve_signal=yc_signal,
            )
            ctx_cache[symbol] = ctx
            return ctx

        tech = compute_technical_snapshot(instr.id, df, date.today())
        swing = detect_swing_setup(instr.id, symbol, df)

        ctx = AlertEvalContext(
            symbol=symbol,
            last_price=float(df["close"].iloc[-1]),
            return_1d=tech.return_1d,
            rsi_14=tech.rsi_14,
            swing_setup_type=swing.setup_type.value if swing.setup_type != SetupType.NO_SETUP else None,
            yield_curve_signal=yc_signal,
        )
        ctx_cache[symbol] = ctx
        return ctx

    fired_list: list[AlertFiredResponse] = []
    skipped_cooldown = 0
    now = datetime.now(tz=timezone.utc)

    for rule in rules:
        ctx = await _get_ctx(rule.canonical_symbol)

        fired = evaluate_rule(
            rule_id=rule.id,
            rule_type=rule.rule_type,
            threshold=float(rule.threshold_value) if rule.threshold_value is not None else None,
            ctx=ctx,
        )
        if fired is None:
            continue

        # Cooldown check
        if not cooldown_ok(rule.last_fired_at, rule.cooldown_hours):
            skipped_cooldown += 1
            continue

        dedup = build_dedup_key(rule.id, fired.fired_at)

        # Upsert ke tabel alerts (dedup_key unique → ON CONFLICT DO NOTHING)
        await db.execute(text("""
            INSERT INTO alerts (id, event_type, instrument_id, materiality, dedup_key, payload, created_at)
            VALUES (:id, :event_type, NULL, 'MEDIUM', :dedup_key, :payload, :now)
            ON CONFLICT (dedup_key) DO NOTHING
        """), {
            "id": new_uuid(),
            "event_type": fired.rule_type,
            "dedup_key": dedup,
            "payload": {"message": fired.message, "value": fired.value, "threshold": fired.threshold},
            "now": now,
        })

        # Update rule stats
        rule.last_fired_at = now
        rule.fire_count = (rule.fire_count or 0) + 1

        # Webhook dispatch (best-effort — tidak gagalkan jika webhook error)
        webhook_sent = False
        if rule.webhook_url:
            payload = build_webhook_payload(fired)
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(rule.webhook_url, json=payload)
                    webhook_sent = resp.status_code < 300
                    if not webhook_sent:
                        log.warning("alert.webhook_failed", rule=rule.id, status=resp.status_code)
            except Exception as exc:
                log.warning("alert.webhook_error", rule=rule.id, error=str(exc))

        fired_list.append(AlertFiredResponse(
            rule_id=rule.id,
            rule_type=fired.rule_type,
            symbol=fired.symbol,
            message=fired.message,
            value=fired.value,
            threshold=fired.threshold,
            fired_at=fired.fired_at,
            dedup_key=dedup,
            webhook_sent=webhook_sent,
        ))

    await db.commit()

    log.info("alerts.evaluated", rules=len(rules), fired=len(fired_list), skipped=skipped_cooldown)

    return AlertEvalResponse(
        rules_checked=len(rules),
        alerts_fired=len(fired_list),
        alerts_skipped_cooldown=skipped_cooldown,
        fired=fired_list,
        as_of=now,
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/history", response_model=list[dict])
async def get_alert_history(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Riwayat 50 alert terakhir yang sudah fired."""
    result = await db.execute(
        select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    )
    alerts = result.scalars().all()
    return [
        {
            "id": a.id,
            "event_type": a.event_type,
            "materiality": a.materiality,
            "dedup_key": a.dedup_key,
            "payload": a.payload,
            "delivered_at": a.delivered_at.isoformat() if a.delivered_at else None,
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]
