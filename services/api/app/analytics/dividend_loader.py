"""
Loader data dividen dari DB untuk R11.

Mengambil FinancialFact + MacroObservation lalu meneruskan ke engine dividend.py.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.dividend import DividendSustainabilityReport, analyze_dividend_sustainability
from app.db.models import FinancialFact, Instrument, MacroObservation

log = structlog.get_logger(__name__)

# Nama metrik di tabel financial_facts
METRIC_DPS = "DPS"                        # Dividen per saham
METRIC_EPS = "EPS"
METRIC_FCF = "FREE_CASH_FLOW"             # FCF total
METRIC_SHARES = "SHARES_OUTSTANDING"

# Series ID MacroObservation untuk inflasi Indonesia & US
SERIES_INFLATION_ID = "BPS_INFLATION_YOY"  # BPS: inflasi YoY Indonesia
SERIES_INFLATION_US = "CPI_YOY_US"


async def load_dividend_analysis(
    db: AsyncSession,
    instrument: Instrument,
    as_of: date,
) -> DividendSustainabilityReport:
    """
    Load data dari DB dan jalankan dividend sustainability analysis.
    Gagal graceful — jika data tidak ada, kembalikan INSUFFICIENT_DATA.
    """
    # ------------------------------------------------------------------
    # Load FinancialFact untuk DPS, EPS, FCF, Shares (3 tahun terakhir)
    # ------------------------------------------------------------------
    cutoff_year = as_of.year - 4  # ambil 4 tahun, pakai 3 terakhir

    facts_result = await db.execute(
        select(FinancialFact)
        .where(
            FinancialFact.instrument_id == instrument.id,
            FinancialFact.metric.in_([METRIC_DPS, METRIC_EPS, METRIC_FCF, METRIC_SHARES]),
            FinancialFact.period_end >= date(cutoff_year, 1, 1),
        )
        .order_by(FinancialFact.period_end.desc())
    )
    facts = list(facts_result.scalars().all())

    # Kelompokkan per metrik per tahun (ambil nilai terbaru per tahun)
    dps_by_year: dict[int, float] = {}
    eps_by_year: dict[int, float] = {}
    fcf_by_year: dict[int, float] = {}
    shares_by_year: dict[int, float] = {}

    for fact in facts:
        if fact.value is None:
            continue
        year = fact.period_end.year
        val = float(fact.value)

        if fact.metric == METRIC_DPS and year not in dps_by_year:
            dps_by_year[year] = val
        elif fact.metric == METRIC_EPS and year not in eps_by_year:
            eps_by_year[year] = val
        elif fact.metric == METRIC_FCF and year not in fcf_by_year:
            fcf_by_year[year] = val
        elif fact.metric == METRIC_SHARES and year not in shares_by_year:
            shares_by_year[year] = val

    # ------------------------------------------------------------------
    # Ambil dividend_yield dari snapshot (dari fundamental loader)
    # Pakai DIVIDEND_YIELD dari FinancialFact terbaru
    # ------------------------------------------------------------------
    yield_result = await db.execute(
        select(FinancialFact)
        .where(
            FinancialFact.instrument_id == instrument.id,
            FinancialFact.metric == "DIVIDEND_YIELD",
        )
        .order_by(FinancialFact.period_end.desc())
        .limit(1)
    )
    yield_fact = yield_result.scalar_one_or_none()
    dividend_yield: Optional[float] = float(yield_fact.value) if yield_fact and yield_fact.value else None

    # ------------------------------------------------------------------
    # Ambil inflasi dari MacroObservation (terkini)
    # ------------------------------------------------------------------
    series_id = SERIES_INFLATION_US if instrument.exchange not in ("IDX", "BEI") else SERIES_INFLATION_ID
    inflation_result = await db.execute(
        select(MacroObservation)
        .where(MacroObservation.series_id == series_id)
        .order_by(MacroObservation.observed_date.desc())
        .limit(1)
    )
    inflation_obs = inflation_result.scalar_one_or_none()
    inflation_rate: Optional[float] = None
    if inflation_obs and inflation_obs.value is not None:
        raw = float(inflation_obs.value)
        # Simpan sebagai desimal: kalau nilainya besar (misal 2.7), konversi ke 0.027
        inflation_rate = raw / 100.0 if raw > 1.0 else raw

    log.debug(
        "dividend.loader",
        symbol=instrument.canonical_symbol,
        dps_years=sorted(dps_by_year),
        inflation_rate=inflation_rate,
    )

    return analyze_dividend_sustainability(
        instrument_id=instrument.id,
        as_of=as_of,
        dps_by_year=dps_by_year,
        eps_by_year=eps_by_year,
        fcf_by_year=fcf_by_year,
        shares_by_year=shares_by_year,
        dividend_yield=dividend_yield,
        inflation_rate=inflation_rate,
    )
