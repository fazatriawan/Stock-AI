"""
R17 — Macro data fetcher.

Sumber data:
1. FRED (Federal Reserve Economic Data) — via public JSON API (tidak butuh key untuk data publik)
   Series yang di-fetch: DFF (Fed Funds Rate), CPIAUCSL (CPI US), T10Y2Y (yield spread 10Y-2Y),
   DGS10 (10Y Treasury yield), DGS2 (2Y Treasury yield), UNRATE (pengangguran US)

2. Data Indonesia — seed manual karena BI/BPS tidak punya API publik yang stabil.
   Series: BI_RATE, CPI_YOY_ID, USD_IDR_JISDOR, GDP_GROWTH_ID

Semua data di-upsert ke tabel macro_observations (INSERT ON CONFLICT DO NOTHING).
Tidak ada scraping sumber yang dilarang oleh syarat penggunaan.
"""
from __future__ import annotations

import httpx
import structlog
from datetime import date, datetime, timezone
from typing import Optional

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# FRED series mapping
# ---------------------------------------------------------------------------

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

FRED_SERIES: dict[str, str] = {
    "FED_FUNDS_RATE": "DFF",         # Federal Funds Rate harian (%)
    "CPI_US_YOY":     "CPIAUCSL",    # CPI All Urban Consumers (level, bukan YoY)
    "YIELD_10Y_2Y":   "T10Y2Y",      # 10Y minus 2Y Treasury yield spread
    "TREASURY_10Y":   "DGS10",       # 10Y Treasury yield
    "TREASURY_2Y":    "DGS2",        # 2Y Treasury yield
    "UNEMPLOYMENT_US":"UNRATE",      # US Unemployment Rate (%)
}

# ---------------------------------------------------------------------------
# Parsed observation
# ---------------------------------------------------------------------------

class MacroPoint:
    __slots__ = ("series_id", "observed_date", "value", "released_at", "source")

    def __init__(self, series_id: str, observed_date: date, value: Optional[float], source: str):
        self.series_id = series_id
        self.observed_date = observed_date
        self.value = value
        self.released_at = datetime.now(tz=timezone.utc)
        self.source = source


# ---------------------------------------------------------------------------
# FRED fetcher (public endpoint, tidak butuh API key untuk 1000 obs terakhir)
# ---------------------------------------------------------------------------

async def fetch_fred_series(
    series_id_local: str,
    fred_series: str,
    limit: int = 5,
    fred_api_key: Optional[str] = None,
) -> list[MacroPoint]:
    """
    Fetch N observasi terbaru dari FRED.
    fred_api_key opsional — tanpa key tetap bisa fetch tapi dibatasi rate.
    """
    params: dict = {
        "series_id": fred_series,
        "sort_order": "desc",
        "limit": str(limit),
        "file_type": "json",
    }
    if fred_api_key:
        params["api_key"] = fred_api_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(FRED_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.warning("fred.fetch_failed", series=fred_series, error=str(exc))
        return []

    points: list[MacroPoint] = []
    for obs in data.get("observations", []):
        raw_value = obs.get("value", ".")
        try:
            val = float(raw_value) if raw_value != "." else None
        except (ValueError, TypeError):
            val = None
        try:
            obs_date = date.fromisoformat(obs["date"])
        except (KeyError, ValueError):
            continue
        points.append(MacroPoint(
            series_id=series_id_local,
            observed_date=obs_date,
            value=val,
            source="src_fred",
        ))

    log.info("fred.fetched", series=fred_series, count=len(points))
    return points


async def fetch_all_fred(fred_api_key: Optional[str] = None) -> list[MacroPoint]:
    """Fetch semua series FRED yang terdaftar."""
    all_points: list[MacroPoint] = []
    for local_id, fred_id in FRED_SERIES.items():
        pts = await fetch_fred_series(local_id, fred_id, limit=3, fred_api_key=fred_api_key)
        all_points.extend(pts)
    return all_points


# ---------------------------------------------------------------------------
# Yield curve analysis (pure, no I/O)
# ---------------------------------------------------------------------------

class YieldCurveSignal:
    NORMAL   = "NORMAL"       # 10Y > 2Y — normal
    FLAT     = "FLAT"         # spread 0–0.5%
    INVERTED = "INVERTED"     # 10Y < 2Y — resesi signal historis

    __slots__ = ("signal", "spread_pct", "treasury_10y", "treasury_2y", "notes")

    def __init__(self, signal: str, spread_pct: Optional[float],
                 treasury_10y: Optional[float], treasury_2y: Optional[float], notes: str):
        self.signal = signal
        self.spread_pct = spread_pct
        self.treasury_10y = treasury_10y
        self.treasury_2y = treasury_2y
        self.notes = notes


def analyze_yield_curve(
    treasury_10y: Optional[float],
    treasury_2y: Optional[float],
) -> YieldCurveSignal:
    """Klasifikasikan bentuk yield curve berdasarkan spread 10Y-2Y."""
    if treasury_10y is None or treasury_2y is None:
        return YieldCurveSignal(
            signal=YieldCurveSignal.NORMAL,
            spread_pct=None,
            treasury_10y=treasury_10y,
            treasury_2y=treasury_2y,
            notes="Data yield tidak tersedia",
        )

    spread = treasury_10y - treasury_2y

    if spread < 0:
        signal = YieldCurveSignal.INVERTED
        notes = (
            f"Yield curve TERBALIK: 10Y={treasury_10y:.2f}% < 2Y={treasury_2y:.2f}% "
            f"(spread={spread:.2f}%). Secara historis mendahului resesi 6–18 bulan."
        )
    elif spread < 0.5:
        signal = YieldCurveSignal.FLAT
        notes = (
            f"Yield curve DATAR: spread={spread:.2f}%. "
            "Potensi perlambatan ekonomi; monitor lebih lanjut."
        )
    else:
        signal = YieldCurveSignal.NORMAL
        notes = (
            f"Yield curve NORMAL: 10Y={treasury_10y:.2f}% > 2Y={treasury_2y:.2f}% "
            f"(spread={spread:.2f}%)."
        )

    return YieldCurveSignal(
        signal=signal,
        spread_pct=round(spread, 4),
        treasury_10y=treasury_10y,
        treasury_2y=treasury_2y,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Macro portfolio impact scorer (pure)
# ---------------------------------------------------------------------------

class MacroImpact:
    __slots__ = ("score", "level", "drivers", "recommendations")

    def __init__(self, score: float, level: str, drivers: list[str], recommendations: list[str]):
        self.score = score        # -1.0 (sangat negatif) → +1.0 (sangat positif)
        self.level = level        # POSITIVE / NEUTRAL / NEGATIVE / SEVERE
        self.drivers = drivers
        self.recommendations = recommendations


def score_macro_impact(
    fed_rate: Optional[float],
    cpi_us: Optional[float],
    yield_curve: Optional[YieldCurveSignal],
    bi_rate: Optional[float],
    usd_idr: Optional[float],
    has_us_exposure: bool = False,
) -> MacroImpact:
    """
    Hitung dampak kondisi makro global terhadap portofolio IDX/US.
    Skala: -1.0 (sangat buruk) → +1.0 (sangat baik).
    """
    score = 0.0
    drivers: list[str] = []
    recommendations: list[str] = []

    # Fed rate — tinggi = negatif untuk saham growth
    if fed_rate is not None:
        if fed_rate >= 5.0:
            score -= 0.3
            drivers.append(f"Fed Funds Rate tinggi ({fed_rate:.2f}%) — cost of capital mahal")
            recommendations.append("Kurangi eksposur saham growth/teknologi US yang valuasinya tinggi")
        elif fed_rate <= 2.0:
            score += 0.2
            drivers.append(f"Fed Funds Rate rendah ({fed_rate:.2f}%) — likuiditas mudah")

    # Yield curve
    if yield_curve is not None:
        if yield_curve.signal == YieldCurveSignal.INVERTED:
            score -= 0.4
            drivers.append(f"Yield curve terbalik (spread={yield_curve.spread_pct:.2f}%) — sinyal resesi")
            recommendations.append("Tambah porsi defensif: dividen tinggi, consumer staples")
        elif yield_curve.signal == YieldCurveSignal.FLAT:
            score -= 0.1
            drivers.append("Yield curve datar — pertumbuhan melambat")

    # BI rate — tinggi = positif untuk bank IDX, negatif untuk properti/konsumer
    if bi_rate is not None:
        if bi_rate >= 6.0:
            score -= 0.1
            drivers.append(f"BI Rate tinggi ({bi_rate:.2f}%) — kredit mahal, konsumer tertekan")
            recommendations.append("Kurangi saham properti & cicilan tinggi; pertimbangkan bank")
        elif bi_rate <= 4.5:
            score += 0.15
            drivers.append(f"BI Rate rendah ({bi_rate:.2f}%) — stimulus ekonomi")

    # USD/IDR — rupiah lemah = negatif untuk importer
    if usd_idr is not None:
        if usd_idr >= 16_500:
            score -= 0.2
            drivers.append(f"Rupiah lemah (USD/IDR={usd_idr:,.0f}) — beban utang USD naik")
            recommendations.append("Hindari emiten dengan utang USD besar; pilih eksportir")
        elif usd_idr <= 15_000:
            score += 0.1
            drivers.append(f"Rupiah kuat (USD/IDR={usd_idr:,.0f})")

    # Clamp
    score = max(-1.0, min(1.0, score))

    if score >= 0.2:
        level = "POSITIVE"
    elif score >= -0.1:
        level = "NEUTRAL"
    elif score >= -0.5:
        level = "NEGATIVE"
    else:
        level = "SEVERE"

    if not drivers:
        drivers.append("Data makro tidak tersedia atau dalam rentang normal")

    return MacroImpact(
        score=round(score, 3),
        level=level,
        drivers=drivers,
        recommendations=recommendations,
    )
