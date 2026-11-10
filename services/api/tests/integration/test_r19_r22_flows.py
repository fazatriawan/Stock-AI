"""
Integration tests untuk R19–R22 flows.

Menggunakan SQLite in-memory via conftest.py.
Test urutan: alert rules CRUD → evaluate → watchlist CRUD → summary.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# R19 — Alert Rules
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_alert_rules_list_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/alerts/rules")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_alert_rule_create_price_above(client: AsyncClient) -> None:
    payload = {
        "rule_type": "price_above",
        "canonical_symbol": "BBCA",
        "threshold_value": 10000.0,
        "cooldown_hours": 24,
    }
    r = await client.post("/api/v1/alerts/rules", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["rule_type"] == "price_above"
    assert body["canonical_symbol"] == "BBCA"
    assert body["threshold_value"] == 10000.0
    assert body["is_active"] is True
    assert body["fire_count"] == 0


@pytest.mark.asyncio
async def test_alert_rule_create_macro_inverted(client: AsyncClient) -> None:
    payload = {"rule_type": "macro_inverted", "cooldown_hours": 72}
    r = await client.post("/api/v1/alerts/rules", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["canonical_symbol"] is None


@pytest.mark.asyncio
async def test_alert_rule_create_invalid_type(client: AsyncClient) -> None:
    r = await client.post("/api/v1/alerts/rules", json={
        "rule_type": "invalid_type_xyz",
        "canonical_symbol": "BBCA",
        "threshold_value": 1000.0,
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_alert_rule_create_missing_threshold(client: AsyncClient) -> None:
    r = await client.post("/api/v1/alerts/rules", json={
        "rule_type": "price_above",
        "canonical_symbol": "BBCA",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_alert_rule_create_missing_symbol(client: AsyncClient) -> None:
    r = await client.post("/api/v1/alerts/rules", json={
        "rule_type": "rsi_above",
        "threshold_value": 70.0,
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_alert_rule_delete(client: AsyncClient) -> None:
    # Create
    r = await client.post("/api/v1/alerts/rules", json={
        "rule_type": "swing_breakout",
        "canonical_symbol": "TLKM",
    })
    assert r.status_code == 201
    rule_id = r.json()["id"]

    # Delete (soft)
    r = await client.delete(f"/api/v1/alerts/rules/{rule_id}")
    assert r.status_code == 204

    # Harus tidak muncul di active rules
    r = await client.get("/api/v1/alerts/rules?active_only=true")
    assert r.status_code == 200
    ids = [rule["id"] for rule in r.json()]
    assert rule_id not in ids


@pytest.mark.asyncio
async def test_alert_evaluate_empty_db(client: AsyncClient) -> None:
    r = await client.post("/api/v1/alerts/evaluate")
    assert r.status_code == 200
    body = r.json()
    assert "rules_checked" in body
    assert "alerts_fired" in body
    assert "as_of" in body


@pytest.mark.asyncio
async def test_alert_history_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/alerts/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# R20 — Watchlist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watchlist_list_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/watchlists")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_watchlist_crud(client: AsyncClient) -> None:
    # CREATE
    r = await client.post("/api/v1/watchlists", json={
        "name": "Top IDX",
        "description": "Saham pilihan IDX",
    })
    assert r.status_code == 201
    wl = r.json()
    wl_id = wl["id"]
    assert wl["name"] == "Top IDX"
    assert wl["item_count"] == 0

    # LIST — harus ada
    r = await client.get("/api/v1/watchlists")
    assert r.status_code == 200
    ids = [w["id"] for w in r.json()]
    assert wl_id in ids

    # GET detail
    r = await client.get(f"/api/v1/watchlists/{wl_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Top IDX"

    # DELETE
    r = await client.delete(f"/api/v1/watchlists/{wl_id}")
    assert r.status_code == 204

    # Verify deleted
    r = await client.get(f"/api/v1/watchlists/{wl_id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_watchlist_add_item_symbol_not_found(client: AsyncClient) -> None:
    # Buat watchlist dulu
    r = await client.post("/api/v1/watchlists", json={"name": "Test WL"})
    wl_id = r.json()["id"]

    # Tambah instrumen yang tidak ada
    r = await client.post(f"/api/v1/watchlists/{wl_id}/items", json={
        "canonical_symbol": "SYMBOL_TIDAK_ADA_XYZ",
    })
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_watchlist_not_found(client: AsyncClient) -> None:
    r = await client.get("/api/v1/watchlists/id-tidak-ada")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# R22 — Summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_returns_structure(client: AsyncClient) -> None:
    r = await client.get("/api/v1/summary")
    assert r.status_code == 200
    body = r.json()
    assert "as_of" in body
    assert "macro" in body
    assert "top_swing_setups" in body
    assert "recent_alerts" in body
    assert "watchlist_near_target" in body


@pytest.mark.asyncio
async def test_summary_macro_block_shape(client: AsyncClient) -> None:
    r = await client.get("/api/v1/summary")
    assert r.status_code == 200
    macro = r.json()["macro"]
    assert "yield_curve_signal" in macro
    assert "macro_impact_score" in macro
    assert "fed_funds_rate" in macro


@pytest.mark.asyncio
async def test_summary_swing_limit_param(client: AsyncClient) -> None:
    r = await client.get("/api/v1/summary?swing_limit=3")
    assert r.status_code == 200
    body = r.json()
    assert len(body["top_swing_setups"]) <= 3


@pytest.mark.asyncio
async def test_portfolio_attribution_endpoint(client: AsyncClient) -> None:
    r = await client.get("/api/v1/portfolio/attribution?benchmark_return_pct=5.0")
    assert r.status_code == 200
    body = r.json()
    assert "portfolio_total_return_pct" in body
    assert "benchmark_return_pct" in body
    assert "positions" in body
    assert "caveat" in body
