"""
R20 — Watchlist & Price Target Engine.

GET    /watchlists                     → Daftar semua watchlist
POST   /watchlists                     → Buat watchlist baru
DELETE /watchlists/{id}                → Hapus watchlist
GET    /watchlists/{id}                → Detail watchlist + items (enriched dengan harga terkini)
POST   /watchlists/{id}/items          → Tambah item ke watchlist
PATCH  /watchlists/{id}/items/{iid}    → Update item (price_target, notes, dll)
DELETE /watchlists/{id}/items/{iid}    → Hapus item dari watchlist
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


from app.api.schemas import (
    WatchlistCreateRequest,
    WatchlistItemAddRequest,
    WatchlistItemResponse,
    WatchlistItemUpdateRequest,
    WatchlistResponse,
)
from app.db.base import new_uuid
from app.db.models import Instrument, PriceBar, Watchlist, WatchlistItem
from app.db.session import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/watchlists", tags=["watchlists"])

_PRICE_DAYS = 5


async def _last_price(instrument_id: str, db: AsyncSession) -> float | None:
    end   = date.today()
    start = end - timedelta(days=_PRICE_DAYS)
    result = await db.execute(
        select(PriceBar.close)
        .where(PriceBar.instrument_id == instrument_id,
               PriceBar.session_date.between(start, end))
        .order_by(PriceBar.session_date.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return float(row) if row is not None else None


def _enrich_item(item: WatchlistItem, instr: Instrument | None, last_price: float | None) -> WatchlistItemResponse:
    target  = float(item.price_target)  if item.price_target  else None
    cost    = float(item.cost_basis)    if item.cost_basis     else None

    pct_to_target  = ((target / last_price) - 1) * 100   if (target and last_price)  else None
    pct_from_cost  = ((last_price / cost)   - 1) * 100   if (cost   and last_price)  else None

    return WatchlistItemResponse(
        id=item.id,
        watchlist_id=item.watchlist_id,
        instrument_id=item.instrument_id,
        canonical_symbol=instr.canonical_symbol if instr else "?",
        company_name=instr.company_name         if instr else None,
        exchange=instr.exchange                 if instr else None,
        notes=item.notes,
        price_target=target,
        target_note=item.target_note,
        cost_basis=cost,
        alert_on_target=item.alert_on_target,
        last_price=last_price,
        pct_to_target=round(pct_to_target, 2) if pct_to_target is not None else None,
        pct_from_cost=round(pct_from_cost, 2) if pct_from_cost is not None else None,
        created_at=item.created_at,
    )


# ---------------------------------------------------------------------------
# Watchlist CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[WatchlistResponse])
async def list_watchlists(db: AsyncSession = Depends(get_db)) -> list[WatchlistResponse]:
    # Hitung item count via subquery agar tidak trigger lazy load
    count_q = (
        select(WatchlistItem.watchlist_id, func.count(WatchlistItem.id).label("cnt"))
        .group_by(WatchlistItem.watchlist_id)
        .subquery()
    )
    result = await db.execute(
        select(Watchlist, func.coalesce(count_q.c.cnt, 0).label("item_count"))
        .outerjoin(count_q, Watchlist.id == count_q.c.watchlist_id)
        .order_by(Watchlist.created_at.desc())
    )
    return [
        WatchlistResponse(
            id=w.id, name=w.name, description=w.description,
            item_count=cnt, items=[], created_at=w.created_at,
        )
        for w, cnt in result.all()
    ]


@router.post("", response_model=WatchlistResponse, status_code=201)
async def create_watchlist(
    body: WatchlistCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    wl = Watchlist(id=new_uuid(), name=body.name, description=body.description)
    db.add(wl)
    await db.commit()
    await db.refresh(wl)
    log.info("watchlist.created", id=wl.id, name=wl.name)
    return WatchlistResponse(id=wl.id, name=wl.name, description=wl.description, created_at=wl.created_at)


@router.delete("/{watchlist_id}", status_code=204, response_model=None)
async def delete_watchlist(watchlist_id: str, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    wl = result.scalar_one_or_none()
    if wl is None:
        raise HTTPException(404, "Watchlist tidak ditemukan")
    await db.delete(wl)
    await db.commit()


# ---------------------------------------------------------------------------
# Watchlist detail (enriched)
# ---------------------------------------------------------------------------

@router.get("/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: str,
    db: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    wl = result.scalar_one_or_none()
    if wl is None:
        raise HTTPException(404, "Watchlist tidak ditemukan")

    items_result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
        .order_by(WatchlistItem.created_at.asc())
    )
    items = items_result.scalars().all()

    enriched: list[WatchlistItemResponse] = []
    for item in items:
        instr_res = await db.execute(select(Instrument).where(Instrument.id == item.instrument_id))
        instr = instr_res.scalar_one_or_none()
        last_p = await _last_price(item.instrument_id, db)
        enriched.append(_enrich_item(item, instr, last_p))

    return WatchlistResponse(
        id=wl.id, name=wl.name, description=wl.description,
        item_count=len(enriched), items=enriched, created_at=wl.created_at,
    )


# ---------------------------------------------------------------------------
# Items CRUD
# ---------------------------------------------------------------------------

@router.post("/{watchlist_id}/items", response_model=WatchlistItemResponse, status_code=201)
async def add_watchlist_item(
    watchlist_id: str,
    body: WatchlistItemAddRequest,
    db: AsyncSession = Depends(get_db),
) -> WatchlistItemResponse:
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Watchlist tidak ditemukan")

    sym = body.canonical_symbol.upper()
    instr_res = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == sym, Instrument.status == "ACTIVE")
    )
    instr = instr_res.scalar_one_or_none()
    if instr is None:
        raise HTTPException(404, f"Instrumen '{sym}' tidak ditemukan")

    # Cek duplikasi
    dup = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.instrument_id == instr.id,
        )
    )
    if dup.scalar_one_or_none() is not None:
        raise HTTPException(409, f"'{sym}' sudah ada di watchlist ini")

    item = WatchlistItem(
        id=new_uuid(),
        watchlist_id=watchlist_id,
        instrument_id=instr.id,
        notes=body.notes,
        price_target=body.price_target,
        target_note=body.target_note,
        cost_basis=body.cost_basis,
        alert_on_target=body.alert_on_target,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    last_p = await _last_price(instr.id, db)
    log.info("watchlist.item_added", watchlist=watchlist_id, symbol=sym)
    return _enrich_item(item, instr, last_p)


@router.patch("/{watchlist_id}/items/{item_id}", response_model=WatchlistItemResponse)
async def update_watchlist_item(
    watchlist_id: str,
    item_id: str,
    body: WatchlistItemUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> WatchlistItemResponse:
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.id == item_id, WatchlistItem.watchlist_id == watchlist_id
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Item tidak ditemukan")

    if body.notes is not None:
        item.notes = body.notes
    if body.price_target is not None:
        item.price_target = Decimal(str(body.price_target))
    if body.target_note is not None:
        item.target_note = body.target_note
    if body.cost_basis is not None:
        item.cost_basis = Decimal(str(body.cost_basis))
    if body.alert_on_target is not None:
        item.alert_on_target = body.alert_on_target

    await db.commit()
    await db.refresh(item)

    instr_res = await db.execute(select(Instrument).where(Instrument.id == item.instrument_id))
    instr = instr_res.scalar_one_or_none()
    last_p = await _last_price(item.instrument_id, db)
    return _enrich_item(item, instr, last_p)


@router.delete("/{watchlist_id}/items/{item_id}", status_code=204, response_model=None)
async def delete_watchlist_item(
    watchlist_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.id == item_id, WatchlistItem.watchlist_id == watchlist_id
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Item tidak ditemukan")
    await db.delete(item)
    await db.commit()
