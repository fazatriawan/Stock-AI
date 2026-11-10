"""
R15 & R17 (MULTI-01, MULTI-02) — Multibagger Discovery & Reverse Scenario Engine.

Mendefinisikan "multibagger kandidat" sebagai kandidat riset (BUKAN sinyal beli otomatis) dengan:
1. Empat Jalur Riset (MULTI-01):
   - QUALITY_COMPOUNDER: ROE tinggi & konsisten, FCF positif, utang rendah
   - EARNINGS_INFLECTION: Akselerasi pertumbuhan pendapatan/laba terhadap historis 3Y
   - TURNAROUND: Valuasi murah (PB/PE rendah) dengan pemulihan FCF/margin & neraca sehat
   - UNDERAPPRECIATED_CATALYST: Diskon signifikan terhadap peer (≥20%) meski profitabilitas kuat
2. Reverse Multibagger Scenario (MULTI-02):
   - Menghitung syarat matematis CAGR EPS untuk target 2x, 3x, 5x, 10x dalam horizon 5 tahun
   - Memperhitungkan stres dilusi saham tahunan dan risiko penurunan permanen (anti-hype)

Scoring: 0–100. Tier: STRONG (≥70), MODERATE (50–69), WEAK (30–49), NOT_QUALIFIED (<30).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MultibaggerTier(str, Enum):
    STRONG = "STRONG"                # skor ≥70
    MODERATE = "MODERATE"            # 50–69
    WEAK = "WEAK"                    # 30–49
    NOT_QUALIFIED = "NOT_QUALIFIED"  # <30
    INSUFFICIENT = "INSUFFICIENT"    # data tidak cukup untuk scoring


class MultibaggerPipeline(str, Enum):
    QUALITY_COMPOUNDER = "QUALITY_COMPOUNDER"
    EARNINGS_INFLECTION = "EARNINGS_INFLECTION"
    TURNAROUND = "TURNAROUND"
    UNDERAPPRECIATED_CATALYST = "UNDERAPPRECIATED_CATALYST"


# ---------------------------------------------------------------------------
# Input snapshot — diisi dari FundamentalSnapshot
# ---------------------------------------------------------------------------

@dataclass
class MultibaggerInput:
    instrument_id: str
    symbol: str
    exchange: str
    sector: Optional[str]

    # Valuasi
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    roe: Optional[float]            # %
    net_margin: Optional[float]     # %
    gross_margin: Optional[float]   # %

    # Pertumbuhan (YoY %)
    revenue_growth_1y: Optional[float]
    revenue_growth_3y: Optional[float]   # CAGR 3 tahun
    eps_growth_1y: Optional[float]
    eps_growth_3y: Optional[float]

    # Leverage
    debt_to_equity: Optional[float]
    current_ratio: Optional[float]

    # FCF
    fcf_yield: Optional[float]           # FCF / Market Cap %
    fcf_margin: Optional[float]          # FCF / Revenue %

    # Teknikal (opsional, untuk tie-breaking)
    price_vs_52w_high: Optional[float]   # 0–1; 1.0 = at 52w high
    relative_strength_1y: Optional[float]  # return 1Y vs benchmark

    # Peer context
    peer_pe_median: Optional[float]
    peer_roe_median: Optional[float]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

@dataclass
class ScoreComponent:
    name: str
    score: float       # 0–25
    max_score: float
    notes: str


@dataclass
class ReverseMultibaggerScenario:
    """MULTI-02: Syarat matematis EPS CAGR & re-rating untuk mencapai target multibagger."""
    target_multiple: int                              # 2, 3, 5, 10
    horizon_years: int                                # mis. 5 tahun
    required_eps_cagr_constant_pe_pct: float          # % CAGR EPS jika P/E tetap
    required_eps_cagr_rerating_pct: Optional[float]   # % CAGR EPS jika P/E menuju target wajar
    assumed_annual_dilution_pct: float                # % asumsi dilusi saham per tahun
    downside_risk_note: str                           # peringatan anti-hype & risiko loss


@dataclass
class MultibaggerScore:
    instrument_id: str
    symbol: str
    tier: MultibaggerTier
    total_score: float          # 0–100
    components: list[ScoreComponent]
    strengths: list[str]
    concerns: list[str]
    data_completeness: float    # 0–1; pct field yang tersedia
    pipelines_matched: list[str] = field(default_factory=list)
    reverse_scenarios: list[ReverseMultibaggerScenario] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------

_BANK_SECTORS = {"Financials", "Banks", "Financial Services"}
_MIN_FIELDS_REQUIRED = 5   # minimal field non-None agar dihitung


def _score_growth(inp: MultibaggerInput) -> ScoreComponent:
    """Revenue & EPS growth: max 25 poin."""
    pts = 0.0
    notes_parts: list[str] = []

    rev1 = inp.revenue_growth_1y
    rev3 = inp.revenue_growth_3y
    eps1 = inp.eps_growth_1y

    # Revenue 1Y
    if rev1 is not None:
        if rev1 >= 25:
            pts += 7
            notes_parts.append(f"rev_1y={rev1:.1f}%✓✓")
        elif rev1 >= 15:
            pts += 5
            notes_parts.append(f"rev_1y={rev1:.1f}%✓")
        elif rev1 >= 5:
            pts += 2
            notes_parts.append(f"rev_1y={rev1:.1f}%")
        else:
            notes_parts.append(f"rev_1y={rev1:.1f}%✗")

    # Revenue 3Y CAGR
    if rev3 is not None:
        if rev3 >= 20:
            pts += 6
            notes_parts.append(f"rev_3y={rev3:.1f}%✓✓")
        elif rev3 >= 10:
            pts += 4
            notes_parts.append(f"rev_3y={rev3:.1f}%✓")
        elif rev3 >= 3:
            pts += 1
            notes_parts.append(f"rev_3y={rev3:.1f}%")

    # EPS growth (lebih penting dari revenue)
    if eps1 is not None:
        if eps1 >= 20:
            pts += 7
            notes_parts.append(f"eps_1y={eps1:.1f}%✓✓")
        elif eps1 >= 10:
            pts += 4
            notes_parts.append(f"eps_1y={eps1:.1f}%✓")
        elif eps1 >= 0:
            pts += 1

    # Akselerasi: rev_1y > rev_3y
    if rev1 and rev3 and rev1 > rev3 * 1.2:
        pts += 5
        notes_parts.append("akselerasi✓")

    pts = min(pts, 25.0)
    return ScoreComponent("growth", pts, 25.0, "; ".join(notes_parts) or "no growth data")


def _score_profitability(inp: MultibaggerInput) -> ScoreComponent:
    """ROE + margin: max 25 poin."""
    pts = 0.0
    notes_parts: list[str] = []

    # ROE
    if inp.roe is not None:
        if inp.roe >= 25:
            pts += 10
            notes_parts.append(f"roe={inp.roe:.1f}%✓✓")
        elif inp.roe >= 15:
            pts += 7
            notes_parts.append(f"roe={inp.roe:.1f}%✓")
        elif inp.roe >= 10:
            pts += 3
            notes_parts.append(f"roe={inp.roe:.1f}%")
        else:
            notes_parts.append(f"roe={inp.roe:.1f}%✗")

    # Net margin
    if inp.net_margin is not None:
        nm = inp.net_margin
        if nm >= 20:
            pts += 8
            notes_parts.append(f"nm={nm:.1f}%✓✓")
        elif nm >= 10:
            pts += 5
            notes_parts.append(f"nm={nm:.1f}%✓")
        elif nm >= 5:
            pts += 2
            notes_parts.append(f"nm={nm:.1f}%")
        else:
            notes_parts.append(f"nm={nm:.1f}%✗")

    # Gross margin
    if inp.gross_margin is not None and inp.gross_margin >= 40:
        pts += 7
        notes_parts.append(f"gm={inp.gross_margin:.1f}%✓")
    elif inp.gross_margin is not None and inp.gross_margin >= 20:
        pts += 3

    pts = min(pts, 25.0)
    return ScoreComponent("profitability", pts, 25.0, "; ".join(notes_parts) or "no margin data")


def _score_balance_sheet(inp: MultibaggerInput) -> ScoreComponent:
    """Leverage + FCF: max 25 poin."""
    pts = 0.0
    notes_parts: list[str] = []
    is_bank = inp.sector in _BANK_SECTORS

    # DER — bank dikecualikan (leverage tinggi adalah normal untuk bank)
    if inp.debt_to_equity is not None and not is_bank:
        der = inp.debt_to_equity
        if der <= 0.3:
            pts += 10
            notes_parts.append(f"der={der:.2f}✓✓")
        elif der <= 0.7:
            pts += 7
            notes_parts.append(f"der={der:.2f}✓")
        elif der <= 1.0:
            pts += 3
            notes_parts.append(f"der={der:.2f}")
        else:
            notes_parts.append(f"der={der:.2f}✗")
    elif is_bank:
        pts += 5  # bank tidak dinilai dari DER
        notes_parts.append("bank:DER-N/A")

    # Current ratio
    if inp.current_ratio is not None:
        if inp.current_ratio >= 2.0:
            pts += 5
            notes_parts.append(f"cr={inp.current_ratio:.1f}✓")
        elif inp.current_ratio >= 1.5:
            pts += 3
        elif inp.current_ratio < 1.0:
            notes_parts.append(f"cr={inp.current_ratio:.1f}✗")

    # FCF yield
    if inp.fcf_yield is not None:
        if inp.fcf_yield >= 5:
            pts += 10
            notes_parts.append(f"fcf_yield={inp.fcf_yield:.1f}%✓✓")
        elif inp.fcf_yield >= 2:
            pts += 6
            notes_parts.append(f"fcf_yield={inp.fcf_yield:.1f}%✓")
        elif inp.fcf_yield > 0:
            pts += 2
            notes_parts.append(f"fcf_yield={inp.fcf_yield:.1f}%")
        else:
            notes_parts.append("fcf_yield<0✗")

    pts = min(pts, 25.0)
    return ScoreComponent("balance_sheet", pts, 25.0, "; ".join(notes_parts) or "no balance sheet data")


def _score_valuation(inp: MultibaggerInput) -> ScoreComponent:
    """Valuasi: max 25 poin. Tidak diskor jika tidak ada PE."""
    pts = 0.0
    notes_parts: list[str] = []

    if inp.pe_ratio is None:
        return ScoreComponent("valuation", 0.0, 25.0, "no PE data")

    pe = inp.pe_ratio
    peer_pe = inp.peer_pe_median

    # PE absolut
    if pe <= 0:
        notes_parts.append(f"pe={pe:.1f}✗ (negatif)")
    elif pe <= 15:
        pts += 15
        notes_parts.append(f"pe={pe:.1f}✓✓")
    elif pe <= 25:
        pts += 10
        notes_parts.append(f"pe={pe:.1f}✓")
    elif pe <= 40:
        pts += 5
        notes_parts.append(f"pe={pe:.1f}")
    else:
        notes_parts.append(f"pe={pe:.1f}✗ (mahal)")

    # PE vs peer
    if peer_pe and peer_pe > 0 and pe > 0:
        discount = (peer_pe - pe) / peer_pe
        if discount >= 0.2:
            pts += 10
            notes_parts.append(f"diskon_peer={discount*100:.0f}%✓✓")
        elif discount >= 0.05:
            pts += 5
            notes_parts.append(f"diskon_peer={discount*100:.0f}%✓")
        elif discount < -0.3:
            pts = max(0.0, pts - 5)
            notes_parts.append(f"premium_peer={-discount*100:.0f}%✗")

    # PB
    if inp.pb_ratio is not None and inp.pb_ratio > 0:
        if inp.pb_ratio <= 1.5:
            pts += 5
            notes_parts.append(f"pb={inp.pb_ratio:.1f}✓")
        elif inp.pb_ratio <= 3.0:
            pts += 2
        elif inp.pb_ratio > 6.0:
            notes_parts.append(f"pb={inp.pb_ratio:.1f}✗")

    pts = min(pts, 25.0)
    return ScoreComponent("valuation", pts, 25.0, "; ".join(notes_parts))


# ---------------------------------------------------------------------------
# MULTI-01: Klasifikasi 4 Pipeline Riset Multibagger
# ---------------------------------------------------------------------------

def classify_multibagger_pipelines(inp: MultibaggerInput) -> list[str]:
    """
    Identifikasi jalur riset multibagger mana yang relevan berdasarkan data fundamental.
    Menghasilkan daftar nama pipeline (kandidat riset, bukan sinyal transaksi).
    """
    matched: list[str] = []
    is_bank = inp.sector in _BANK_SECTORS
    healthy_debt = is_bank or (inp.debt_to_equity is not None and inp.debt_to_equity <= 0.7)

    # 1. Quality Compounder: ROE ≥ 15%, growth positif, FCF positif, utang sehat
    if (
        inp.roe is not None
        and inp.roe >= 15.0
        and healthy_debt
        and ((inp.revenue_growth_1y is not None and inp.revenue_growth_1y >= 10.0)
             or (inp.eps_growth_1y is not None and inp.eps_growth_1y >= 10.0))
        and (inp.fcf_yield is None or inp.fcf_yield > 0)
    ):
        matched.append(MultibaggerPipeline.QUALITY_COMPOUNDER.value)

    # 2. Earnings Inflection: akselerasi 1Y di atas 3Y atau lonjakan EPS ≥ 20%
    rev_inflection = (
        inp.revenue_growth_1y is not None
        and inp.revenue_growth_3y is not None
        and inp.revenue_growth_1y >= 15.0
        and inp.revenue_growth_1y > inp.revenue_growth_3y * 1.15
    )
    eps_inflection = (
        inp.eps_growth_1y is not None
        and inp.eps_growth_1y >= 20.0
        and (inp.eps_growth_3y is None or inp.eps_growth_1y > inp.eps_growth_3y * 1.15)
    )
    if rev_inflection or eps_inflection:
        matched.append(MultibaggerPipeline.EARNINGS_INFLECTION.value)

    # 3. Turnaround: valuasi tertekan (PB ≤ 1.5 atau PE ≤ 12) + FCF/margin positif & utang aman
    low_val = (
        (inp.pb_ratio is not None and 0 < inp.pb_ratio <= 1.5)
        or (inp.pe_ratio is not None and 0 < inp.pe_ratio <= 12.0)
    )
    positive_cash_or_margin = (
        (inp.fcf_yield is not None and inp.fcf_yield >= 2.0)
        or (inp.net_margin is not None and inp.net_margin >= 8.0)
    )
    if low_val and positive_cash_or_margin and healthy_debt:
        matched.append(MultibaggerPipeline.TURNAROUND.value)

    # 4. Underappreciated Catalyst: diskon ≥ 20% terhadap peer PE + ROE ≥ 12%
    if (
        inp.pe_ratio is not None
        and inp.pe_ratio > 0
        and inp.peer_pe_median is not None
        and inp.peer_pe_median > 0
        and inp.pe_ratio <= inp.peer_pe_median * 0.80
        and (inp.roe is not None and inp.roe >= 12.0)
    ):
        matched.append(MultibaggerPipeline.UNDERAPPRECIATED_CATALYST.value)

    return matched


# ---------------------------------------------------------------------------
# MULTI-02: Reverse Multibagger Scenario (2x, 3x, 5x, 10x)
# ---------------------------------------------------------------------------

def compute_reverse_multibagger_scenarios(
    inp: MultibaggerInput,
    horizon_years: int = 5,
    annual_dilution_pct: float = 2.0,
    target_multiples: tuple[int, ...] = (2, 3, 5, 10),
) -> list[ReverseMultibaggerScenario]:
    """
    Hitung syarat pertumbuhan EPS tahunan (CAGR) untuk mencapai return 2x, 3x, 5x, 10x
    dalam `horizon_years` tahun, dengan memperhitungkan dilusi tahunan.
    Tidak menetapkan probabilitas tanpa kalibrasi (PRD §11 MULTI-02).
    """
    if horizon_years < 1:
        horizon_years = 5

    dilution_factor = (1.0 + annual_dilution_pct / 100.0) ** horizon_years
    current_pe = inp.pe_ratio if (inp.pe_ratio and inp.pe_ratio > 0) else None
    target_pe = inp.peer_pe_median if (inp.peer_pe_median and inp.peer_pe_median > 0) else 15.0

    scenarios: list[ReverseMultibaggerScenario] = []
    for mult in target_multiples:
        # Total pertumbuhan laba yang dibutuhkan pada P/E tetap, dikompensasi dilusi saham
        total_earnings_multiple = float(mult) * dilution_factor
        req_cagr_const = ((total_earnings_multiple ** (1.0 / horizon_years)) - 1.0) * 100.0

        req_cagr_rerating: Optional[float] = None
        if current_pe is not None and current_pe > 0 and target_pe > 0:
            rerating_ratio = target_pe / current_pe
            adj_multiple = max(0.1, total_earnings_multiple / rerating_ratio)
            req_cagr_rerating = ((adj_multiple ** (1.0 / horizon_years)) - 1.0) * 100.0

        if req_cagr_const > 35.0:
            risk_note = (
                f"Butuh EPS CAGR {req_cagr_const:.1f}%/thn selama {horizon_years} thn — sangat agresif; "
                "risiko kompresi multiple & kegagalan eksekusi tinggi."
            )
        else:
            risk_note = (
                f"Asumsi dilusi {annual_dilution_pct:.1f}%/thn; jika ROE/FCF memburuk atau "
                "terjadi right issue dilutif, tesis batal dan berisiko rugi permanen."
            )

        scenarios.append(ReverseMultibaggerScenario(
            target_multiple=mult,
            horizon_years=horizon_years,
            required_eps_cagr_constant_pe_pct=round(req_cagr_const, 2),
            required_eps_cagr_rerating_pct=(
                round(req_cagr_rerating, 2) if req_cagr_rerating is not None else None
            ),
            assumed_annual_dilution_pct=annual_dilution_pct,
            downside_risk_note=risk_note,
        ))

    return scenarios


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def score_multibagger(inp: MultibaggerInput) -> MultibaggerScore:
    """Hitung skor multibagger dari snapshot fundamental."""
    # Hitung data completeness
    all_fields = [
        inp.pe_ratio, inp.roe, inp.net_margin, inp.gross_margin,
        inp.revenue_growth_1y, inp.eps_growth_1y, inp.debt_to_equity,
        inp.fcf_yield, inp.pb_ratio, inp.current_ratio,
    ]
    available = sum(1 for f in all_fields if f is not None)
    completeness = available / len(all_fields)

    if available < _MIN_FIELDS_REQUIRED:
        return MultibaggerScore(
            instrument_id=inp.instrument_id,
            symbol=inp.symbol,
            tier=MultibaggerTier.INSUFFICIENT,
            total_score=0.0,
            components=[],
            strengths=[],
            concerns=["Data fundamental tidak cukup untuk scoring"],
            data_completeness=completeness,
            pipelines_matched=[],
            reverse_scenarios=[],
        )

    components = [
        _score_growth(inp),
        _score_profitability(inp),
        _score_balance_sheet(inp),
        _score_valuation(inp),
    ]

    total = sum(c.score for c in components)

    # Tier
    if total >= 70:
        tier = MultibaggerTier.STRONG
    elif total >= 50:
        tier = MultibaggerTier.MODERATE
    elif total >= 30:
        tier = MultibaggerTier.WEAK
    else:
        tier = MultibaggerTier.NOT_QUALIFIED

    # Strengths & concerns
    strengths: list[str] = []
    concerns: list[str] = []

    if inp.roe and inp.roe >= 20:
        strengths.append(f"ROE tinggi ({inp.roe:.1f}%)")
    if inp.revenue_growth_1y and inp.revenue_growth_1y >= 20:
        strengths.append(f"Revenue tumbuh {inp.revenue_growth_1y:.1f}% YoY")
    if inp.net_margin and inp.net_margin >= 15:
        strengths.append(f"Net margin sehat ({inp.net_margin:.1f}%)")
    if inp.fcf_yield and inp.fcf_yield >= 3:
        strengths.append(f"FCF yield {inp.fcf_yield:.1f}%")
    if inp.debt_to_equity is not None and inp.debt_to_equity <= 0.3 and inp.sector not in _BANK_SECTORS:
        strengths.append(f"Utang sangat rendah (DER={inp.debt_to_equity:.2f})")

    if inp.pe_ratio and inp.pe_ratio > 40:
        concerns.append(f"Valuasi mahal (PE={inp.pe_ratio:.1f}x)")
    if inp.roe is not None and inp.roe < 10:
        concerns.append(f"ROE rendah ({inp.roe:.1f}%)")
    if inp.revenue_growth_1y is not None and inp.revenue_growth_1y < 0:
        concerns.append(f"Revenue turun {inp.revenue_growth_1y:.1f}% YoY")
    if inp.debt_to_equity is not None and inp.debt_to_equity > 1.5 and inp.sector not in _BANK_SECTORS:
        concerns.append(f"Leverage tinggi (DER={inp.debt_to_equity:.2f})")
    if inp.fcf_yield is not None and inp.fcf_yield < 0:
        concerns.append("FCF negatif")

    pipelines = classify_multibagger_pipelines(inp)
    scenarios = compute_reverse_multibagger_scenarios(inp)

    return MultibaggerScore(
        instrument_id=inp.instrument_id,
        symbol=inp.symbol,
        tier=tier,
        total_score=round(total, 1),
        components=components,
        strengths=strengths,
        concerns=concerns,
        data_completeness=round(completeness, 2),
        pipelines_matched=pipelines,
        reverse_scenarios=scenarios,
    )
