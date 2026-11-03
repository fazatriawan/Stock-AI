"""
Macro & Policy routes.

GET /macro/observations  → Snapshot terbaru per series makroekonomi
GET /macro/events        → Event kebijakan & dampak per sektor/perusahaan
POST /macro/events       → Tambah event manual
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    MacroObservationResponse,
    MacroSnapshotResponse,
    PolicyEventResponse,
    PolicyEventListResponse,
    PolicyEventCreateRequest,
)
from app.db.models import Event, EventCompanyImpact, Instrument, MacroObservation
from app.db.session import get_db
from app.db.base import new_uuid

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/macro", tags=["macro"])

# Label ramah untuk series_id yang umum
SERIES_LABELS: dict[str, str] = {
    "BI_RATE": "BI Rate",
    "CPI_YOY": "Inflasi CPI (YoY)",
    "USD_IDR": "Kurs USD/IDR",
    "GDP_GROWTH": "Pertumbuhan PDB",
    "CAR_BANKING": "CAR Perbankan",
    "NPL_BANKING": "NPL Gross Perbankan",
    "JCI": "IHSG",
    "LQ45": "LQ45",
    "CREDIT_GROWTH": "Pertumbuhan Kredit",
    "M2_GROWTH": "Pertumbuhan M2",
}


@router.get("/observations", response_model=MacroSnapshotResponse)
async def get_macro_snapshot(
    db: AsyncSession = Depends(get_db),
) -> MacroSnapshotResponse:
    """
    Snapshot terbaru per series makroekonomi dari tabel macro_observations.
    Mengembalikan satu nilai terbaru per series_id.
    """
    result = await db.execute(
        select(MacroObservation).order_by(MacroObservation.observed_date.desc())
    )
    all_obs = result.scalars().all()

    # Ambil satu data terbaru per series
    seen: set[str] = set()
    snapshots: list[MacroObservationResponse] = []
    for obs in all_obs:
        if obs.series_id in seen:
            continue
        seen.add(obs.series_id)
        snapshots.append(MacroObservationResponse(
            series_id=obs.series_id,
            label=SERIES_LABELS.get(obs.series_id, obs.series_id),
            value=float(obs.value) if obs.value is not None else None,
            observed_date=obs.observed_date,
            released_at=obs.released_at,
        ))

    # Sort: label dikenal dulu, lalu alphabetical
    known_order = list(SERIES_LABELS.keys())
    snapshots.sort(key=lambda s: (
        known_order.index(s.series_id) if s.series_id in known_order else 999,
        s.series_id
    ))

    return MacroSnapshotResponse(
        observations=snapshots,
        total_series=len(snapshots),
        as_of=datetime.now(tz=timezone.utc),
    )


@router.get("/events", response_model=PolicyEventListResponse)
async def list_policy_events(
    limit: int = Query(30, ge=1, le=100),
    materiality: Optional[str] = Query(None, description="LOW / MEDIUM / HIGH"),
    country: Optional[str] = Query(None, description="ID, US, dll"),
    db: AsyncSession = Depends(get_db),
) -> PolicyEventListResponse:
    """
    Event kebijakan dan dampak ke perusahaan/sektor.
    Diurutkan dari yang paling baru.
    """
    query = select(Event).order_by(Event.published_at.desc().nullslast(), Event.created_at.desc())
    if materiality:
        query = query.where(Event.materiality == materiality)
    if country:
        query = query.where(Event.country == country)
    query = query.limit(limit)

    result = await db.execute(query)
    events = result.scalars().all()

    responses: list[PolicyEventResponse] = []
    for ev in events:
        # Load company impacts
        impacts_result = await db.execute(
            select(EventCompanyImpact)
            .where(EventCompanyImpact.event_id == ev.id)
        )
        impacts = impacts_result.scalars().all()

        # Resolve canonical symbols
        impact_list: list[dict] = []
        for imp in impacts:
            instr_result = await db.execute(
                select(Instrument).where(Instrument.id == imp.instrument_id)
            )
            instr = instr_result.scalar_one_or_none()
            impact_list.append({
                "canonical_symbol": instr.canonical_symbol if instr else imp.instrument_id,
                "company_name": instr.company_name if instr else None,
                "sign": imp.sign,
                "exposure": imp.exposure,
                "mechanism": imp.mechanism,
                "confidence": imp.confidence,
            })

        responses.append(PolicyEventResponse(
            id=ev.id,
            event_type=ev.event_type,
            title=ev.title,
            summary=ev.summary,
            country=ev.country,
            affected_sectors=ev.affected_sectors or [],
            effective_date=ev.effective_date,
            published_at=ev.published_at,
            policy_stage=ev.policy_stage,
            materiality=ev.materiality,
            company_impacts=impact_list,
        ))

    return PolicyEventListResponse(
        events=responses,
        total=len(responses),
        as_of=datetime.now(tz=timezone.utc),
    )


@router.post("/events", response_model=PolicyEventResponse, status_code=201)
async def create_policy_event(
    body: PolicyEventCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> PolicyEventResponse:
    """
    Tambah event kebijakan secara manual.
    Berguna untuk mencatat rapat BI, perubahan regulasi, dll.
    """
    event = Event(
        id=new_uuid(),
        event_type=body.event_type,
        title=body.title,
        summary=body.summary,
        country=body.country,
        affected_sectors=body.affected_sectors,
        effective_date=body.effective_date,
        published_at=body.published_at or datetime.now(tz=timezone.utc),
        policy_stage=body.policy_stage,
        materiality=body.materiality,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    log.info("macro.event_created", event_id=event.id, title=event.title)

    return PolicyEventResponse(
        id=event.id,
        event_type=event.event_type,
        title=event.title,
        summary=event.summary,
        country=event.country,
        affected_sectors=event.affected_sectors or [],
        effective_date=event.effective_date,
        published_at=event.published_at,
        policy_stage=event.policy_stage,
        materiality=event.materiality,
        company_impacts=[],
    )
