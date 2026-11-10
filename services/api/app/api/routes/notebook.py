"""
Research Notebook routes.

GET    /notebook         → list catatan riset (filter symbol/tag/search)
POST   /notebook         → buat catatan baru
GET    /notebook/{id}    → detail catatan
PATCH  /notebook/{id}    → update judul/isi/tags
DELETE /notebook/{id}    → hapus catatan
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    NoteCreateRequest,
    NoteUpdateRequest,
    NoteResponse,
)
from app.db.models import ResearchNote
from app.db.session import get_db
from app.db.base import new_uuid

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/notebook", tags=["notebook"])


def _to_response(note: ResearchNote) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        title=note.title,
        body=note.body,
        canonical_symbol=note.canonical_symbol,
        tags=note.tags or [],
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    symbol: Optional[str] = Query(None, description="Filter berdasarkan canonical_symbol"),
    tag: Optional[str] = Query(None, description="Filter berdasarkan tag"),
    search: Optional[str] = Query(None, description="Cari di judul & isi"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[NoteResponse]:
    query = select(ResearchNote).order_by(ResearchNote.updated_at.desc())

    if symbol:
        sym = symbol.upper()
        sym_canonical = sym if ":" in sym else f"IDX:{sym}"
        query = query.where(ResearchNote.canonical_symbol == sym_canonical)

    query = query.limit(limit)
    result = await db.execute(query)
    notes = result.scalars().all()

    out = [_to_response(n) for n in notes]

    # Filter tag & search di Python (JSON array dan fulltext tidak mudah di SQLite/PG tanpa index)
    if tag:
        out = [n for n in out if tag in (n.tags or [])]
    if search:
        s = search.lower()
        out = [n for n in out if s in n.title.lower() or s in n.body.lower()]

    return out


@router.post("", response_model=NoteResponse, status_code=201)
async def create_note(
    body: NoteCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> NoteResponse:
    sym = None
    if body.canonical_symbol:
        sym = body.canonical_symbol.upper()
        if ":" not in sym:
            sym = f"IDX:{sym}"

    note = ResearchNote(
        id=new_uuid(),
        title=body.title,
        body=body.body or "",
        canonical_symbol=sym,
        tags=body.tags or [],
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    log.info("notebook.created", note_id=note.id, title=note.title)
    return _to_response(note)


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(note_id: str, db: AsyncSession = Depends(get_db)) -> NoteResponse:
    note = await db.get(ResearchNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    return _to_response(note)


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    body: NoteUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> NoteResponse:
    note = await db.get(ResearchNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")

    if body.title is not None:
        note.title = body.title
    if body.body is not None:
        note.body = body.body
    if body.tags is not None:
        note.tags = body.tags
    if body.canonical_symbol is not None:
        sym = body.canonical_symbol.upper()
        note.canonical_symbol = sym if ":" in sym else f"IDX:{sym}"

    await db.commit()
    await db.refresh(note)
    return _to_response(note)


@router.delete("/{note_id}", status_code=204, response_class=Response)
async def delete_note(note_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    note = await db.get(ResearchNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    await db.delete(note)
    await db.commit()
    return Response(status_code=204)
