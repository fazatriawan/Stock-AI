"""
Dividend Sustainability Analysis — R11.

Menjawab: "Apakah dividen ini berkelanjutan, dan berapa real return setelah inflasi?"

Checks:
  1. Payout ratio — DPS/EPS; ideal 20-80%; > 100% tidak sustainable
  2. FCF coverage — DPS per saham vs FCF per saham (lebih konservatif dari EPS)
  3. Trend dividen — 3 tahun terakhir: tumbuh / stabil / turun / dipotong
  4. Real yield — dividend_yield dikurangi inflasi terkini
  5. Dividend growth rate (DGR) — CAGR 3-tahun DPS

Input data: FinancialFact records + MacroObservation untuk inflasi.
Semua input berasal dari data terverifikasi — TIDAK ada angka LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class DividendTrend(str, Enum):
    GROWING = "GROWING"        # DPS meningkat 3 tahun berturut-turut
    STABLE = "STABLE"          # DPS berubah < 5% per tahun
    DECLINING = "DECLINING"    # DPS turun setidaknya 1 tahun
    CUT = "CUT"                # DPS turun > 20% (1 tahun)
    INITIATED = "INITIATED"    # Baru mulai dividen (< 2 tahun data)
    NO_DATA = "NO_DATA"


class SustainabilityRating(str, Enum):
    STRONG = "STRONG"          # Semua checks hijau
    ADEQUATE = "ADEQUATE"      # Sebagian besar checks hijau
    WEAK = "WEAK"              # Payout tinggi atau FCF lemah
    UNSUSTAINABLE = "UNSUSTAINABLE"  # Payout > 100% atau dipotong
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class DividendPoint:
    """Satu titik data dividen per tahun."""
    year: int
    dps: float               # dividen per saham
    eps: Optional[float]
    fcf_per_share: Optional[float]
    payout_ratio: Optional[float]   # DPS / EPS
    fcf_payout_ratio: Optional[float]  # DPS / FCF_per_share


@dataclass
class DividendSustainabilityReport:
    """
    Laporan sustainability dividen lengkap.
    Data-driven — tidak ada angka karangan LLM.
    """
    instrument_id: str
    as_of: date

    # Status ringkas
    rating: SustainabilityRating
    trend: DividendTrend

    # Metrik kunci
    latest_dps: Optional[float] = None
    latest_yield: Optional[float] = None        # dividend_yield dari fundamental
    payout_ratio: Optional[float] = None        # DPS / EPS terkini
    fcf_payout_ratio: Optional[float] = None    # DPS / FCF per share terkini
    dgr_3y: Optional[float] = None              # Dividend Growth Rate 3 tahun (CAGR)

    # Real return
    inflation_rate: Optional[float] = None      # dari MacroObservation terkini
    real_yield: Optional[float] = None          # dividend_yield - inflation_rate

    # Data historis (3 tahun terakhir)
    history: list[DividendPoint] = field(default_factory=list)

    # Penjelasan
    notes: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cagr(start: float, end: float, years: int) -> Optional[float]:
    """CAGR dari start ke end selama n tahun. None jika tidak valid."""
    if years <= 0 or start <= 0 or end < 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def _classify_trend(history: list[DividendPoint]) -> DividendTrend:
    """Klasifikasi tren dari titik data historis (sorted ascending by year)."""
    dps_values = [h.dps for h in history if h.dps >= 0]
    if len(dps_values) < 2:
        return DividendTrend.NO_DATA if not dps_values else DividendTrend.INITIATED

    if len(dps_values) < 3:
        return DividendTrend.INITIATED

    latest = dps_values[-1]
    prev = dps_values[-2]
    oldest = dps_values[0]

    # Cut: turun > 20% dalam 1 tahun terakhir
    if prev > 0 and (prev - latest) / prev > 0.20:
        return DividendTrend.CUT

    # Semua naik → GROWING
    if all(dps_values[i] <= dps_values[i + 1] for i in range(len(dps_values) - 1)):
        # Tumbuh minimal 1%
        if oldest > 0 and (latest - oldest) / oldest > 0.01:
            return DividendTrend.GROWING

    # Stabil: semua perubahan < 5%
    changes = []
    for i in range(1, len(dps_values)):
        if dps_values[i - 1] > 0:
            changes.append(abs(dps_values[i] - dps_values[i - 1]) / dps_values[i - 1])
    if changes and max(changes) < 0.05:
        return DividendTrend.STABLE

    # Ada penurunan
    if any(dps_values[i] < dps_values[i - 1] for i in range(1, len(dps_values))):
        return DividendTrend.DECLINING

    return DividendTrend.STABLE


def _rate_sustainability(
    payout: Optional[float],
    fcf_payout: Optional[float],
    trend: DividendTrend,
    latest_dps: Optional[float],
) -> SustainabilityRating:
    if latest_dps is None or latest_dps <= 0:
        return SustainabilityRating.INSUFFICIENT_DATA

    if trend == DividendTrend.NO_DATA:
        return SustainabilityRating.INSUFFICIENT_DATA

    # Hard UNSUSTAINABLE
    if payout is not None and payout > 1.0:
        return SustainabilityRating.UNSUSTAINABLE
    if fcf_payout is not None and fcf_payout > 1.0:
        return SustainabilityRating.UNSUSTAINABLE
    if trend == DividendTrend.CUT:
        return SustainabilityRating.UNSUSTAINABLE

    # WEAK
    if payout is not None and payout > 0.80:
        return SustainabilityRating.WEAK
    if trend == DividendTrend.DECLINING:
        return SustainabilityRating.WEAK

    # STRONG: payout sehat + tren positif
    if (
        payout is not None and 0.20 <= payout <= 0.60
        and trend in (DividendTrend.GROWING, DividendTrend.STABLE)
    ):
        return SustainabilityRating.STRONG

    return SustainabilityRating.ADEQUATE


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze_dividend_sustainability(
    *,
    instrument_id: str,
    as_of: date,
    # Data dari FinancialFact (sudah di-load di luar)
    dps_by_year: dict[int, float],       # {tahun: DPS}
    eps_by_year: dict[int, float],       # {tahun: EPS}
    fcf_by_year: dict[int, float],       # {tahun: FCF total}
    shares_by_year: dict[int, float],    # {tahun: jumlah saham beredar}
    # Dari FundamentalSnapshot
    dividend_yield: Optional[float],
    # Dari MacroObservation
    inflation_rate: Optional[float],     # misal: 0.027 untuk 2.7% YoY
) -> DividendSustainabilityReport:
    """
    Analisis dividend sustainability dari data terverifikasi.
    Tidak ada angka karangan — semua berasal dari FinancialFact + MacroObservation.
    """
    notes: list[str] = []
    data_gaps: list[str] = []

    if not dps_by_year:
        return DividendSustainabilityReport(
            instrument_id=instrument_id,
            as_of=as_of,
            rating=SustainabilityRating.INSUFFICIENT_DATA,
            trend=DividendTrend.NO_DATA,
            data_gaps=["Tidak ada data DPS (dividen per saham)"],
        )

    # Ambil 3 tahun terakhir
    sorted_years = sorted(dps_by_year.keys())[-3:]
    history: list[DividendPoint] = []

    for year in sorted_years:
        dps = dps_by_year[year]
        eps = eps_by_year.get(year)
        shares = shares_by_year.get(year)
        fcf = fcf_by_year.get(year)

        fcf_per_share: Optional[float] = None
        if fcf is not None and shares and shares > 0:
            fcf_per_share = fcf / shares

        payout = None
        if eps and eps > 0 and dps >= 0:
            payout = dps / eps
        elif eps and eps <= 0 and dps > 0:
            payout = float("inf")  # EPS negatif → payout tidak terbatas

        fcf_payout = None
        if fcf_per_share and fcf_per_share > 0 and dps >= 0:
            fcf_payout = dps / fcf_per_share
        elif fcf_per_share and fcf_per_share <= 0 and dps > 0:
            fcf_payout = float("inf")

        history.append(DividendPoint(
            year=year,
            dps=dps,
            eps=eps,
            fcf_per_share=fcf_per_share,
            payout_ratio=None if payout == float("inf") else payout,
            fcf_payout_ratio=None if fcf_payout == float("inf") else fcf_payout,
        ))

    # Metrik terkini
    latest = history[-1]
    latest_dps = latest.dps
    payout_ratio = latest.payout_ratio
    fcf_payout_ratio = latest.fcf_payout_ratio

    if payout_ratio is None and latest.eps and latest.eps <= 0:
        notes.append(f"EPS negatif di {latest.year} — payout ratio tidak bermakna")

    # Trend
    trend = _classify_trend(history)

    # DGR 3 tahun
    dgr_3y: Optional[float] = None
    if len(sorted_years) >= 2:
        oldest_dps = dps_by_year[sorted_years[0]]
        years_span = sorted_years[-1] - sorted_years[0]
        dgr_3y = _cagr(oldest_dps, latest_dps, years_span)

    # Real yield
    real_yield: Optional[float] = None
    if dividend_yield is not None and inflation_rate is not None:
        real_yield = dividend_yield - inflation_rate

    # Rating
    # Clamp payout ke float untuk rating (inf = None di atas sudah ditangani)
    rating = _rate_sustainability(payout_ratio, fcf_payout_ratio, trend, latest_dps)

    # Notes
    if payout_ratio is not None:
        if payout_ratio > 1.0:
            notes.append(f"Payout ratio {payout_ratio:.0%} melebihi 100% — dividen dibayar dari modal/utang")
        elif payout_ratio > 0.80:
            notes.append(f"Payout ratio {payout_ratio:.0%} tinggi — sedikit ruang untuk pertumbuhan")
        elif payout_ratio < 0.20 and latest_dps > 0:
            notes.append(f"Payout ratio {payout_ratio:.0%} rendah — potensi kenaikan dividen di masa depan")

    if real_yield is not None:
        if real_yield < 0:
            notes.append(f"Real yield negatif ({real_yield:.2%}) — return dividen di bawah inflasi")
        elif real_yield > 0.05:
            notes.append(f"Real yield menarik ({real_yield:.2%}) di atas inflasi")

    if dgr_3y is not None and dgr_3y > 0:
        notes.append(f"DGR 3 tahun: +{dgr_3y:.1%}/tahun")
    elif dgr_3y is not None and dgr_3y < 0:
        notes.append(f"DGR 3 tahun: {dgr_3y:.1%}/tahun (negatif)")

    if trend == DividendTrend.CUT:
        notes.append("Dividen dipotong > 20% dalam 1 tahun terakhir — sinyal tekanan keuangan")

    # Data gaps
    if inflation_rate is None:
        data_gaps.append("Data inflasi tidak tersedia — real yield tidak bisa dihitung")
    if not eps_by_year:
        data_gaps.append("Data EPS tidak tersedia — payout ratio tidak bisa dihitung")
    if not fcf_by_year:
        data_gaps.append("Data FCF tidak tersedia — FCF coverage tidak bisa dihitung")
    if len(sorted_years) < 3:
        data_gaps.append(f"Hanya {len(sorted_years)} tahun data DPS — tren kurang reliable")

    return DividendSustainabilityReport(
        instrument_id=instrument_id,
        as_of=as_of,
        rating=rating,
        trend=trend,
        latest_dps=latest_dps,
        latest_yield=dividend_yield,
        payout_ratio=payout_ratio,
        fcf_payout_ratio=fcf_payout_ratio,
        dgr_3y=dgr_3y,
        inflation_rate=inflation_rate,
        real_yield=real_yield,
        history=history,
        notes=notes,
        data_gaps=data_gaps,
    )
