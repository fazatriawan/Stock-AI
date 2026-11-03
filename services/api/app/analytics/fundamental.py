"""
Fundamental metrics aggregator.
Mengambil financial_facts dari database dan menghitung metrik per sektor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FinancialFact, Instrument


@dataclass
class FundamentalSnapshot:
    instrument_id: str
    as_of: date
    sector: Optional[str] = None
    # Universal
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    roe: Optional[float] = None
    eps: Optional[float] = None
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    dividend_yield: Optional[float] = None
    debt_to_equity: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    beta: Optional[float] = None
    # Bank-specific
    nim: Optional[float] = None
    npl_gross: Optional[float] = None
    car: Optional[float] = None
    ldr: Optional[float] = None
    casa_ratio: Optional[float] = None
    cost_of_credit: Optional[float] = None
    # Coverage
    metrics_available: list[str] = field(default_factory=list)
    metrics_missing: list[str] = field(default_factory=list)
    period_end: Optional[date] = None
    data_freshness: str = "UNKNOWN"


METRIC_FIELD_MAP: dict[str, str] = {
    "PE_RATIO": "pe_ratio",
    "P/B": "pb_ratio",
    "ROE": "roe",
    "EPS_TRAILING": "eps",
    "EPS": "eps",
    "REVENUE": "revenue",
    "NET_INCOME": "net_income",
    "MARKET_CAP": "market_cap",
    "ENTERPRISE_VALUE": "enterprise_value",
    "DIVIDEND_YIELD": "dividend_yield",
    "DEBT_TO_EQUITY": "debt_to_equity",
    "GROSS_MARGIN": "gross_margin",
    "OPERATING_MARGIN": "operating_margin",
    "BETA": "beta",
    # Bank
    "NIM": "nim",
    "NPL_GROSS": "npl_gross",
    "CAR": "car",
    "LDR": "ldr",
    "CASA_RATIO": "casa_ratio",
    "COST_OF_CREDIT": "cost_of_credit",
}

BANK_REQUIRED = {"ROE", "NIM", "NPL_GROSS", "CAR", "P/B"}
GENERAL_REQUIRED = {"PE_RATIO", "ROE", "REVENUE", "NET_INCOME", "EPS"}


async def load_fundamental_snapshot(
    db: AsyncSession,
    instrument: Instrument,
    as_of: date,
) -> FundamentalSnapshot:
    """Ambil snapshot fundamental terbaru per tanggal as_of."""
    snap = FundamentalSnapshot(
        instrument_id=instrument.id,
        as_of=as_of,
        sector=instrument.sector,
    )

    # Ambil fact terbaru per metric yang available_at <= as_of
    result = await db.execute(
        select(FinancialFact)
        .where(
            FinancialFact.instrument_id == instrument.id,
            FinancialFact.available_at <= as_of,
        )
        .order_by(FinancialFact.period_end.desc(), FinancialFact.available_at.desc())
    )
    facts = result.scalars().all()

    # Ambil satu fact per metric (yang paling baru)
    seen_metrics: set[str] = set()
    for fact in facts:
        metric = fact.metric.upper()
        if metric in seen_metrics:
            continue
        seen_metrics.add(metric)

        field_name = METRIC_FIELD_MAP.get(metric)
        if field_name and fact.value is not None:
            setattr(snap, field_name, float(fact.value))
            snap.metrics_available.append(metric)
            if snap.period_end is None:
                snap.period_end = fact.period_end

    # Evaluasi coverage berdasarkan sektor
    is_bank = instrument.sector == "Financials" and instrument.industry == "Banks"
    required = BANK_REQUIRED if is_bank else GENERAL_REQUIRED
    snap.metrics_missing = [m for m in required if m not in seen_metrics]

    # Data freshness
    if snap.period_end:
        age_days = (as_of - snap.period_end).days
        if age_days <= 120:
            snap.data_freshness = "FRESH"
        elif age_days <= 400:
            snap.data_freshness = "ACCEPTABLE"
        else:
            snap.data_freshness = "STALE"

    return snap


def coverage_score(snap: FundamentalSnapshot) -> float:
    """Skor coverage 0-1 dari fundamental snapshot."""
    is_bank = snap.sector == "Financials"
    required = BANK_REQUIRED if is_bank else GENERAL_REQUIRED
    available = set(snap.metrics_available)
    if not required:
        return 0.0
    return len(required & available) / len(required)
