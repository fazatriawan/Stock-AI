"""
Decision Journal routes — Phase 5.

GET    /journal          → list[JournalEntryResponse]
POST   /journal          → JournalEntryResponse (201)
GET    /journal/{id}     → JournalEntryResponse
PATCH  /journal/{id}/review  → JournalEntryResponse (outcome + notes)
DELETE /journal/{id}     → 204
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    JournalEntryCreateRequest,
    JournalEntryResponse,
    JournalReviewRequest,
)
from app.db.models import TradeJournal
from app.db.session import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("", response_model=list[JournalEntryResponse])
async def list_journal(
    symbol: str | None = None,
    action: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[JournalEntryResponse]:
    """Daftar semua catatan keputusan, terbaru dulu."""
    q = select(TradeJournal).order_by(TradeJournal.decision_date.desc(), TradeJournal.created_at.desc())
    if symbol:
        q = q.where(TradeJournal.canonical_symbol == symbol.upper())
    if action:
        q = q.where(TradeJournal.action == action.upper())
    q = q.limit(min(limit, 200))

    result = await db.execute(q)
    entries = result.scalars().all()
    return [JournalEntryResponse.model_validate(e) for e in entries]


@router.post("", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_journal_entry(
    body: JournalEntryCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    """Tambah catatan keputusan baru."""
    entry = TradeJournal(
        id=str(uuid.uuid4()),
        canonical_symbol=body.canonical_symbol.upper(),
        decision_date=body.decision_date,
        action=body.action,
        rationale=body.rationale,
        thesis=body.thesis,
        invalidation=body.invalidation,
        price_at_decision=body.price_at_decision,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)

    log.info("journal.created", symbol=entry.canonical_symbol, action=entry.action)
    return JournalEntryResponse.model_validate(entry)


@router.get("/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    result = await db.execute(select(TradeJournal).where(TradeJournal.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    return JournalEntryResponse.model_validate(entry)


@router.patch("/{entry_id}/review", response_model=JournalEntryResponse)
async def review_journal_entry(
    entry_id: str,
    body: JournalReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    """Review keputusan: apakah keputusan itu benar?"""
    result = await db.execute(select(TradeJournal).where(TradeJournal.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")

    entry.outcome = body.outcome
    entry.outcome_notes = body.outcome_notes
    entry.reviewed_at = datetime.now(tz=timezone.utc)
    await db.flush()
    await db.refresh(entry)

    log.info("journal.reviewed", id=entry_id, outcome=body.outcome)
    return JournalEntryResponse.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journal_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(TradeJournal).where(TradeJournal.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    await db.delete(entry)
    log.info("journal.deleted", id=entry_id)
