"""
Smoke tests untuk semua route utama.

Memastikan setiap endpoint merespons dengan status code yang benar
(tidak 500) saat database kosong. Tidak memerlukan PostgreSQL nyata.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Health / Root
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_root(client: AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "Stock Intelligence API"


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_data_health(client: AsyncClient) -> None:
    r = await client.get("/api/v1/data/health")
    assert r.status_code == 200
    body = r.json()
    assert "providers" in body
    assert "checked_at" in body


# ---------------------------------------------------------------------------
# Instruments / Markets
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_instruments_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/instruments")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert "items" in body or isinstance(body, list)


@pytest.mark.asyncio
async def test_market_status(client: AsyncClient) -> None:
    r = await client.get("/api/v1/markets/status")
    # Boleh 200 atau 404 jika tidak ada exchange terdaftar, tapi tidak boleh 500
    assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_portfolio_summary_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/portfolio")
    # DB kosong: bisa 200 (empty portfolio) atau 404 (belum ada portfolio)
    assert r.status_code in (200, 404)


@pytest.mark.asyncio
async def test_portfolio_trades_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/portfolio/trades")
    assert r.status_code in (200, 404)


@pytest.mark.asyncio
async def test_portfolio_performance_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/portfolio/performance")
    assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Decisions / Screener
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decisions_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/decisions")
    assert r.status_code == 200
    body = r.json()
    assert "decisions" in body
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_screener_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/screener")
    assert r.status_code == 200
    body = r.json()
    assert "results" in body


# ---------------------------------------------------------------------------
# Macro
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_macro_snapshot_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/macro/observations")
    assert r.status_code == 200
    body = r.json()
    assert "observations" in body
    assert body["total_series"] == 0


@pytest.mark.asyncio
async def test_macro_events_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/macro/events")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_macro_create_event(client: AsyncClient) -> None:
    payload = {
        "event_type": "MONETARY_POLICY",
        "title": "BI menaikkan suku bunga 25 bps",
        "materiality": "HIGH",
        "country": "ID",
    }
    r = await client.post("/api/v1/macro/events", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == payload["title"]
    assert body["materiality"] == "HIGH"


# ---------------------------------------------------------------------------
# Notebook
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notebook_list_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/notebook")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_notebook_crud(client: AsyncClient) -> None:
    # CREATE
    r = await client.post("/api/v1/notebook", json={
        "title": "Analisis BBCA",
        "body": "Fundamental kuat, ROE konsisten di atas 15%.",
        "canonical_symbol": "BBCA",
        "tags": ["banking", "bluechip"],
    })
    assert r.status_code == 201
    note = r.json()
    note_id = note["id"]
    assert note["title"] == "Analisis BBCA"
    assert note["canonical_symbol"] == "IDX:BBCA"
    assert "banking" in note["tags"]

    # READ
    r = await client.get(f"/api/v1/notebook/{note_id}")
    assert r.status_code == 200
    assert r.json()["id"] == note_id

    # UPDATE
    r = await client.patch(f"/api/v1/notebook/{note_id}", json={"title": "Analisis BBCA — Update"})
    assert r.status_code == 200
    assert r.json()["title"] == "Analisis BBCA — Update"

    # DELETE
    r = await client.delete(f"/api/v1/notebook/{note_id}")
    assert r.status_code == 204

    # Verify deleted
    r = await client.get(f"/api/v1/notebook/{note_id}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Daily
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daily_intelligence_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/daily")
    # DB kosong — bisa 200 dengan data kosong atau 404
    assert r.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_journal_list_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/journal")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_journal_create(client: AsyncClient) -> None:
    payload = {
        "canonical_symbol": "IDX:BBRI",
        "decision_date": "2024-01-15",
        "action": "BUY",
        "rationale": "Valuasi menarik setelah koreksi 15%.",
    }
    r = await client.post("/api/v1/journal", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["action"] == "BUY"
    assert body["canonical_symbol"] == "IDX:BBRI"
