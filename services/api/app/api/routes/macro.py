"""
Macro & Policy routes.

GET  /macro/observations           → Snapshot terbaru per series
GET  /macro/yield-curve            → Analisis yield curve US (NORMAL/FLAT/INVERTED)
GET  /macro/impact                 → Dampak makro terhadap portofolio IDX/US
POST /macro/observations/refresh   → Fetch data terbaru dari FRED
POST /macro/observations/upsert    → Input manual satu observasi
GET  /macro/events                 → Event kebijakan
POST /macro/events                 → Tambah event manual
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    MacroObservationResponse,
    MacroSnapshotResponse,
    PolicyEventResponse,
    PolicyEventListResponse,
    PolicyEventCreateRequest,
    MacroRefreshResponse,
    YieldCurveResponse,
    MacroImpactResponse,
    MacroObservationUpsertRequest,
)
from app.db.models import Event, EventCompanyImpact, Instrument, MacroObservation
from app.db.session import get_db
from app.db.base import new_uuid
from app.ingestion.macro_fetcher import (
    fetch_all_fred,
    analyze_yield_curve,
    score_macro_impact,
)

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


# ---------------------------------------------------------------------------
# R17: Yield curve endpoint
# ---------------------------------------------------------------------------

@router.get("/yield-curve", response_model=YieldCurveResponse)
async def get_yield_curve(db: AsyncSession = Depends(get_db)) -> YieldCurveResponse:
    """
    Analisis yield curve US berdasarkan data TREASURY_10Y dan TREASURY_2Y terbaru di DB.
    Signal: NORMAL (10Y>2Y), FLAT (spread<0.5%), INVERTED (10Y<2Y — sinyal resesi historis).
    """
    async def _latest(series_id: str) -> Optional[float]:
        res = await db.execute(
            select(MacroObservation)
            .where(MacroObservation.series_id == series_id)
            .order_by(MacroObservation.observed_date.desc())
            .limit(1)
        )
        obs = res.scalar_one_or_none()
        return float(obs.value) if obs and obs.value is not None else None

    t10 = await _latest("TREASURY_10Y")
    t2  = await _latest("TREASURY_2Y")

    # Fallback: coba ambil dari YIELD_10Y_2Y (spread langsung dari FRED)
    spread_direct = await _latest("YIELD_10Y_2Y")
    if t10 is None and t2 is None and spread_direct is not None:
        t10 = spread_direct + 0.0   # hanya ada spread; estimasi kasar
        t2  = 0.0

    yc = analyze_yield_curve(t10, t2)

    return YieldCurveResponse(
        signal=yc.signal,
        spread_pct=yc.spread_pct,
        treasury_10y=yc.treasury_10y,
        treasury_2y=yc.treasury_2y,
        notes=yc.notes,
        as_of=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# R17: Macro impact scorer
# ---------------------------------------------------------------------------

@router.get("/impact", response_model=MacroImpactResponse)
async def get_macro_impact(
    has_us_exposure: bool = Query(False, description="True jika portofolio punya saham US"),
    db: AsyncSession = Depends(get_db),
) -> MacroImpactResponse:
    """
    Skor dampak kondisi makro global terhadap portofolio.
    Skala: -1.0 (sangat buruk) → +1.0 (sangat baik untuk saham).
    """
    async def _latest(series_id: str) -> Optional[float]:
        res = await db.execute(
            select(MacroObservation)
            .where(MacroObservation.series_id == series_id)
            .order_by(MacroObservation.observed_date.desc())
            .limit(1)
        )
        obs = res.scalar_one_or_none()
        return float(obs.value) if obs and obs.value is not None else None

    fed_rate = await _latest("FED_FUNDS_RATE")
    bi_rate  = await _latest("BI_RATE")
    usd_idr  = await _latest("USD_IDR")
    t10      = await _latest("TREASURY_10Y")
    t2       = await _latest("TREASURY_2Y")

    yc = analyze_yield_curve(t10, t2)
    impact = score_macro_impact(
        fed_rate=fed_rate,
        cpi_us=None,
        yield_curve=yc,
        bi_rate=bi_rate,
        usd_idr=usd_idr,
        has_us_exposure=has_us_exposure,
    )

    return MacroImpactResponse(
        score=impact.score,
        level=impact.level,
        drivers=impact.drivers,
        recommendations=impact.recommendations,
        yield_curve=YieldCurveResponse(
            signal=yc.signal,
            spread_pct=yc.spread_pct,
            treasury_10y=yc.treasury_10y,
            treasury_2y=yc.treasury_2y,
            notes=yc.notes,
            as_of=datetime.now(tz=timezone.utc),
        ),
        fed_rate=fed_rate,
        bi_rate=bi_rate,
        usd_idr=usd_idr,
        as_of=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# R17: FRED refresh
# ---------------------------------------------------------------------------

@router.post("/observations/refresh", response_model=MacroRefreshResponse)
async def refresh_macro_observations(db: AsyncSession = Depends(get_db)) -> MacroRefreshResponse:
    """
    Fetch data terbaru dari FRED (Federal Reserve Economic Data).
    Data yang di-fetch: Fed Funds Rate, yield 10Y/2Y, CPI US, pengangguran US.

    Rate limit FRED public API: ~1000 req/hari. Endpoint ini fetch ±6 series × 3 obs = 18 req.
    Gunakan FRED_API_KEY di .env untuk meningkatkan limit (opsional, gratis di fred.stlouisfed.org).
    """
    from app.core.config import get_settings
    settings = get_settings()
    fred_key = getattr(settings, "fred_api_key", None)

    # Seed src_fred jika belum ada
    await db.execute(text("""
        INSERT INTO sources (id, url, publisher, title, license_class, primary_or_secondary)
        VALUES ('src_fred', 'https://fred.stlouisfed.org', 'Federal Reserve (FRED)',
                'FRED macro data', 'THIRD_PARTY', 'SECONDARY')
        ON CONFLICT (id) DO NOTHING
    """))

    points = await fetch_all_fred(fred_api_key=fred_key)

    inserted = 0
    skipped  = 0
    errors: list[str] = []
    series_seen: set[str] = set()

    for pt in points:
        series_seen.add(pt.series_id)
        try:
            result = await db.execute(text("""
                INSERT INTO macro_observations
                    (series_id, observed_date, value, released_at, source_id)
                VALUES (:series_id, :observed_date, :value, :released_at, 'src_fred')
                ON CONFLICT (series_id, observed_date, vintage_at) DO NOTHING
            """), {
                "series_id":    pt.series_id,
                "observed_date": pt.observed_date,
                "value":        pt.value,
                "released_at":  pt.released_at,
            })
            if getattr(result, "rowcount", 0) > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as exc:
            errors.append(f"{pt.series_id}@{pt.observed_date}: {exc}")

    await db.commit()
    log.info("macro.refresh_done", inserted=inserted, skipped=skipped)

    return MacroRefreshResponse(
        inserted=inserted,
        skipped=skipped,
        series_fetched=sorted(series_seen),
        errors=errors,
        as_of=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# R17: Manual upsert
# ---------------------------------------------------------------------------

@router.post("/observations/upsert", response_model=MacroObservationResponse, status_code=201)
async def upsert_macro_observation(
    body: MacroObservationUpsertRequest,
    db: AsyncSession = Depends(get_db),
) -> MacroObservationResponse:
    """
    Input manual satu observasi makro (BI Rate, kurs, dll).
    Berguna untuk data Indonesia yang tidak ada di FRED.
    """
    from app.core.config import get_settings  # noqa: F401

    # Seed src_manual
    await db.execute(text("""
        INSERT INTO sources (id, url, publisher, title, license_class, primary_or_secondary)
        VALUES ('src_manual', NULL, 'Manual Entry', 'data diinput manual', 'THIRD_PARTY', 'SECONDARY')
        ON CONFLICT (id) DO NOTHING
    """))

    now = datetime.now(tz=timezone.utc)
    await db.execute(text("""
        INSERT INTO macro_observations
            (series_id, observed_date, value, released_at, vintage_at, source_id)
        VALUES (:series_id, :observed_date, :value, :now, :now, 'src_manual')
        ON CONFLICT (series_id, observed_date, vintage_at) DO NOTHING
    """), {
        "series_id":     body.series_id,
        "observed_date": body.observed_date,
        "value":         body.value,
        "now":           now,
    })
    await db.commit()

    log.info("macro.manual_upsert", series_id=body.series_id, date=str(body.observed_date))

    return MacroObservationResponse(
        series_id=body.series_id,
        label=SERIES_LABELS.get(body.series_id, body.series_id),
        value=body.value,
        observed_date=body.observed_date,
        released_at=now,
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
            title=ev.title or "",
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
        title=event.title or "",
        summary=event.summary,
        country=event.country,
        affected_sectors=event.affected_sectors or [],
        effective_date=event.effective_date,
        published_at=event.published_at,
        policy_stage=event.policy_stage,
        materiality=event.materiality,
        company_impacts=[],
    )
