"""
Portfolio analyzer — Phase 3.
Menghitung health score, konsentrasi, diversifikasi, dan analisis posisi rugi.

Semua kalkulasi deterministik — tidak ada LLM di sini.
LLM hanya boleh menambah narasi, tidak boleh mengubah skor atau rekomendasi.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.portfolio.calculator import PositionData


# ---------------------------------------------------------------------------
# Thresholds (bisa jadi config di masa depan)
# ---------------------------------------------------------------------------

MAX_SINGLE_WEIGHT = 0.25       # > 25% = overweight
MAX_SINGLE_WEIGHT_SEVERE = 0.40  # > 40% = severely overweight
MAX_SECTOR_WEIGHT = 0.50       # > 50% = sector concentration
MIN_POSITIONS_DIVERSIFIED = 5   # < 5 posisi = undiversified
LOSS_THRESHOLD = -0.05         # rugi > 5% = masuk loss analyzer


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------

class HealthGrade(str, Enum):
    EXCELLENT = "EXCELLENT"   # 80–100
    GOOD = "GOOD"             # 60–79
    FAIR = "FAIR"             # 40–59
    POOR = "POOR"             # 0–39


@dataclass
class ConcentrationRisk:
    symbol: str
    weight: float
    severity: str       # NORMAL / OVERWEIGHT / SEVERELY_OVERWEIGHT
    message: str


@dataclass
class SectorRisk:
    sector: str
    weight: float
    severity: str       # NORMAL / CONCENTRATED
    message: str


@dataclass
class PortfolioHealthReport:
    """Laporan kesehatan portofolio — hasil kalkulasi deterministik."""
    health_score: float          # 0–100
    grade: HealthGrade

    position_count: int
    diversification_score: float   # 0–100 (herfindahl-based)
    concentration_risks: list[ConcentrationRisk]
    sector_risks: list[SectorRisk]

    largest_position_symbol: Optional[str]
    largest_position_weight: float

    total_invested: float
    total_market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    # Komponen skor
    diversification_component: float   # 0–40 poin
    concentration_component: float     # 0–30 poin (penalty)
    pnl_component: float               # 0–30 poin

    warnings: list[str]
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Loss analysis
# ---------------------------------------------------------------------------

class LossScenario(str, Enum):
    CUT_LOSS = "CUT_LOSS"
    PARTIAL_CUT = "PARTIAL_CUT"
    HOLD_WAIT = "HOLD_WAIT"
    AVERAGE_DOWN = "AVERAGE_DOWN"
    STOP_LOSS = "STOP_LOSS"


@dataclass
class LossScenarioAnalysis:
    scenario: LossScenario
    label: str
    description: str

    # Angka hipotetis jika skenario dijalankan hari ini
    projected_loss_idr: float       # loss yang direalisasi (negatif)
    projected_loss_pct: float
    remaining_exposure_idr: float   # paparan yang tersisa setelah aksi
    breakeven_price: Optional[float]  # harga impas (jika avg down)

    pros: list[str]
    cons: list[str]
    risk_level: str   # LOW / MEDIUM / HIGH


@dataclass
class LossPositionAnalysis:
    canonical_symbol: str
    company_name: Optional[str]

    shares: float
    lots: float
    avg_cost: float
    current_price: float
    total_cost: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    scenarios: list[LossScenarioAnalysis]
    suggested_scenario: LossScenario
    suggested_reason: str


# ---------------------------------------------------------------------------
# Health calculator
# ---------------------------------------------------------------------------

def compute_portfolio_health(
    positions: dict[str, PositionData],
    sector_weights: dict[str, float],
) -> PortfolioHealthReport:
    """
    Hitung health score portofolio.

    Komponen (total 100 poin):
    - Diversification (40 poin): berdasarkan Herfindahl index
    - Concentration penalty (30 poin): dikurangi jika ada overweight
    - P/L component (30 poin): berdasarkan unrealized P/L keseluruhan
    """
    if not positions:
        return PortfolioHealthReport(
            health_score=0.0,
            grade=HealthGrade.POOR,
            position_count=0,
            diversification_score=0.0,
            concentration_risks=[],
            sector_risks=[],
            largest_position_symbol=None,
            largest_position_weight=0.0,
            total_invested=0.0,
            total_market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            diversification_component=0.0,
            concentration_component=0.0,
            pnl_component=0.0,
            warnings=["Portofolio kosong"],
            recommendations=["Tambahkan posisi pertama untuk memulai analisis"],
        )

    n = len(positions)
    weights = [p.weight for p in positions.values() if p.weight > 0]

    # --- Herfindahl-Hirschman Index (HHI) ---
    # HHI = sum of squared weights; lower = more diversified
    # HHI range: 1/n (perfect diversified) to 1 (fully concentrated)
    hhi = sum(w ** 2 for w in weights) if weights else 1.0
    # Normalize diversification: 1 position → 0, n ≥ 8 positions with equal weight → 100
    max_div_score = 100.0
    if n >= 8 and abs(hhi - 1 / n) < 0.01:
        div_score = max_div_score
    else:
        # Score 0–100: lower HHI = higher score
        # Perfect = 1/n, worst = 1
        # normalized = (1 - hhi) / (1 - 1/n) if n > 1 else 0
        if n > 1:
            normalized = (1.0 - hhi) / (1.0 - 1.0 / n)
        else:
            normalized = 0.0
        div_score = round(min(100.0, max(0.0, normalized * 100.0)), 1)

    # --- Diversification component (0–40) ---
    if n < MIN_POSITIONS_DIVERSIFIED:
        # Penalty proportional to how far below minimum
        div_component = div_score * 0.4 * (n / MIN_POSITIONS_DIVERSIFIED)
    else:
        div_component = div_score * 0.4

    # --- Concentration risks ---
    concentration_risks: list[ConcentrationRisk] = []
    concentration_penalty = 0.0

    sorted_positions = sorted(positions.values(), key=lambda p: p.weight, reverse=True)
    largest = sorted_positions[0] if sorted_positions else None

    for pos in sorted_positions:
        if pos.weight >= MAX_SINGLE_WEIGHT_SEVERE:
            severity = "SEVERELY_OVERWEIGHT"
            penalty = 30.0
            msg = f"{pos.canonical_symbol} {pos.weight*100:.1f}% — jauh melebihi batas 25%"
        elif pos.weight >= MAX_SINGLE_WEIGHT:
            severity = "OVERWEIGHT"
            penalty = 15.0
            msg = f"{pos.canonical_symbol} {pos.weight*100:.1f}% — melebihi batas 25%"
        else:
            continue

        concentration_risks.append(ConcentrationRisk(
            symbol=pos.canonical_symbol,
            weight=pos.weight,
            severity=severity,
            message=msg,
        ))
        concentration_penalty = max(concentration_penalty, penalty)

    concentration_component = 30.0 - concentration_penalty

    # --- Sector risks ---
    sector_risks: list[SectorRisk] = []
    for sector, sw in sector_weights.items():
        if sw > MAX_SECTOR_WEIGHT:
            sector_risks.append(SectorRisk(
                sector=sector,
                weight=sw,
                severity="CONCENTRATED",
                message=f"Sektor {sector} {sw*100:.1f}% — melebihi batas 50%",
            ))

    # --- P/L component (0–30) ---
    total_cost = sum(p.total_cost for p in positions.values())
    total_mv = sum(p.market_value for p in positions.values() if p.market_value is not None)
    total_pnl = total_mv - total_cost if total_mv > 0 else 0.0
    total_pnl_pct = total_pnl / total_cost if total_cost > 0 else 0.0

    # Mapping P/L% ke komponen:
    # >= +20%  → 30
    # >= +5%   → 25
    # 0 to +5% → 20
    # -5 to 0% → 15
    # < -5%    → max(0, 15 + pnl_pct * 100)
    if total_pnl_pct >= 0.20:
        pnl_component = 30.0
    elif total_pnl_pct >= 0.05:
        pnl_component = 25.0
    elif total_pnl_pct >= 0.0:
        pnl_component = 20.0
    elif total_pnl_pct >= -0.05:
        pnl_component = 15.0
    else:
        pnl_component = max(0.0, 15.0 + total_pnl_pct * 100.0)

    # --- Total score ---
    health_score = round(div_component + concentration_component + pnl_component, 1)
    health_score = max(0.0, min(100.0, health_score))

    if health_score >= 80:
        grade = HealthGrade.EXCELLENT
    elif health_score >= 60:
        grade = HealthGrade.GOOD
    elif health_score >= 40:
        grade = HealthGrade.FAIR
    else:
        grade = HealthGrade.POOR

    # --- Warnings & Recommendations ---
    warnings: list[str] = []
    recommendations: list[str] = []

    for r in concentration_risks:
        warnings.append(r.message)
        recommendations.append(f"Pertimbangkan mengurangi posisi {r.symbol.split(':')[-1]}")

    for s in sector_risks:
        warnings.append(s.message)
        recommendations.append(f"Pertimbangkan diversifikasi ke sektor lain selain {s.sector}")

    if n < MIN_POSITIONS_DIVERSIFIED:
        warnings.append(f"Hanya {n} posisi — portofolio kurang terdiversifikasi")
        recommendations.append(f"Tambahkan minimal {MIN_POSITIONS_DIVERSIFIED - n} saham dari sektor berbeda")

    if total_pnl_pct < -0.10:
        warnings.append(f"Portofolio rugi {abs(total_pnl_pct)*100:.1f}% — review tesis investasi")

    return PortfolioHealthReport(
        health_score=health_score,
        grade=grade,
        position_count=n,
        diversification_score=div_score,
        concentration_risks=concentration_risks,
        sector_risks=sector_risks,
        largest_position_symbol=largest.canonical_symbol if largest else None,
        largest_position_weight=largest.weight if largest else 0.0,
        total_invested=total_cost,
        total_market_value=total_mv if total_mv > 0 else total_cost,
        unrealized_pnl=round(total_pnl, 2),
        unrealized_pnl_pct=round(total_pnl_pct, 4),
        diversification_component=round(div_component, 1),
        concentration_component=round(concentration_component, 1),
        pnl_component=round(pnl_component, 1),
        warnings=warnings,
        recommendations=recommendations,
    )


# ---------------------------------------------------------------------------
# Loss analyzer
# ---------------------------------------------------------------------------

def analyze_loss_position(pos: PositionData) -> Optional[LossPositionAnalysis]:
    """
    Analisis 5 skenario untuk posisi yang sedang rugi.
    Return None jika posisi tidak merugi.
    """
    if pos.current_price is None or pos.unrealized_pnl_pct is None:
        return None

    pnl_pct = pos.unrealized_pnl_pct
    if pnl_pct >= LOSS_THRESHOLD:
        return None  # tidak merugi cukup signifikan

    cp = pos.current_price
    avg = pos.avg_cost
    total_cost = pos.total_cost
    mv = pos.market_value or (cp * pos.shares)
    pnl = mv - total_cost
    shares = pos.shares

    scenarios: list[LossScenarioAnalysis] = []

    # --- Skenario 1: Cut Loss ---
    scenarios.append(LossScenarioAnalysis(
        scenario=LossScenario.CUT_LOSS,
        label="Cut Loss",
        description="Jual semua posisi sekarang, realisasikan kerugian, alokasikan ulang modal.",
        projected_loss_idr=round(pnl, 0),
        projected_loss_pct=round(pnl_pct, 4),
        remaining_exposure_idr=0.0,
        breakeven_price=None,
        pros=[
            "Menghentikan potensi kerugian lebih lanjut",
            "Modal dapat dialokasikan ke peluang lebih baik",
            "Menetapkan kerugian untuk keperluan pajak (tax-loss harvesting)",
        ],
        cons=[
            "Kerugian menjadi permanen",
            "Kehilangan potensi recovery jika tesis masih valid",
            "Biaya transaksi",
        ],
        risk_level="LOW",
    ))

    # --- Skenario 2: Partial Cut (50%) ---
    half_shares = shares / 2
    half_cost = total_cost / 2
    half_mv = cp * half_shares
    half_pnl = half_mv - half_cost
    scenarios.append(LossScenarioAnalysis(
        scenario=LossScenario.PARTIAL_CUT,
        label="Partial Cut (50%)",
        description="Jual separuh posisi untuk mengurangi risiko, pertahankan sisa untuk kemungkinan recovery.",
        projected_loss_idr=round(half_pnl, 0),
        projected_loss_pct=round(pnl_pct, 4),  # same % loss on the portion sold
        remaining_exposure_idr=round(half_mv, 0),
        breakeven_price=None,
        pros=[
            "Mengurangi eksposur risiko 50%",
            "Tetap berpartisipasi jika ada recovery",
            "Modal sebagian bebas untuk realokasi",
        ],
        cons=[
            "Masih menanggung setengah kerugian jika turun terus",
            "Kompleksitas pencatatan cost basis",
        ],
        risk_level="MEDIUM",
    ))

    # --- Skenario 3: Hold & Wait ---
    scenarios.append(LossScenarioAnalysis(
        scenario=LossScenario.HOLD_WAIT,
        label="Hold & Tunggu",
        description="Tidak ada aksi — pertahankan posisi dan tunggu recovery berdasarkan tesis.",
        projected_loss_idr=round(pnl, 0),
        projected_loss_pct=round(pnl_pct, 4),
        remaining_exposure_idr=round(mv, 0),
        breakeven_price=round(avg, 2),
        pros=[
            "Tidak merealisasikan kerugian",
            "Cocok jika tesis investasi masih intact",
            "Tidak ada biaya transaksi",
        ],
        cons=[
            "Risiko kerugian lebih dalam jika fundamental memburuk",
            "Opportunity cost — modal terikat",
            "Bisa menimbulkan bias psikologis (anchoring ke avg cost)",
        ],
        risk_level="HIGH",
    ))

    # --- Skenario 4: Average Down (beli lagi sebanyak posisi saat ini) ---
    # Jika beli lagi sebanyak shares saat ini di harga cp:
    add_shares = shares
    add_cost = add_shares * cp
    new_total_shares = shares + add_shares
    new_total_cost = total_cost + add_cost
    new_avg = new_total_cost / new_total_shares
    scenarios.append(LossScenarioAnalysis(
        scenario=LossScenario.AVERAGE_DOWN,
        label="Average Down",
        description=f"Tambah posisi sebesar {round(add_shares/100)} lot lagi di harga saat ini untuk menurunkan avg cost.",
        projected_loss_idr=0.0,  # belum ada realisasi
        projected_loss_pct=0.0,
        remaining_exposure_idr=round(new_total_cost, 0),
        breakeven_price=round(new_avg, 2),
        pros=[
            f"Avg cost turun dari {avg:,.0f} → {new_avg:,.0f}",
            "Lebih mudah mencapai breakeven",
            "Cocok jika fundamental kuat dan penurunan bersifat sementara",
        ],
        cons=[
            "Menggandakan eksposur modal yang sudah merugi",
            "Jika harga turun lagi, kerugian total jauh lebih besar",
            f"Membutuhkan tambahan modal ≈ Rp {add_cost:,.0f}",
        ],
        risk_level="HIGH",
    ))

    # --- Skenario 5: Stop Loss (jual jika turun 5% lagi) ---
    stop_price = round(cp * 0.95, 0)
    stop_mv = stop_price * shares
    stop_pnl = stop_mv - total_cost
    stop_pnl_pct = stop_pnl / total_cost if total_cost > 0 else 0.0
    scenarios.append(LossScenarioAnalysis(
        scenario=LossScenario.STOP_LOSS,
        label="Stop Loss (-5%)",
        description=f"Tetapkan level stop loss di Rp {stop_price:,.0f} (−5% dari harga saat ini). Jual otomatis jika tercapai.",
        projected_loss_idr=round(stop_pnl, 0),
        projected_loss_pct=round(stop_pnl_pct, 4),
        remaining_exposure_idr=round(mv, 0),
        breakeven_price=round(avg, 2),
        pros=[
            "Membatasi kerugian maksimal yang dapat ditoleransi",
            "Disiplin manajemen risiko",
            "Tetap hold jika harga tidak turun ke stop level",
        ],
        cons=[
            "Bisa ter-trigger oleh volatilitas sementara",
            "Membutuhkan monitoring aktif",
        ],
        risk_level="MEDIUM",
    ))

    # --- Rekomendasi skenario berdasarkan severity ---
    abs_pnl = abs(pnl_pct)
    if abs_pnl >= 0.20:
        # Rugi berat (> 20%): sarankan cut loss
        suggested = LossScenario.CUT_LOSS
        reason = f"Kerugian {abs_pnl*100:.1f}% sudah material. Pertimbangkan cut loss untuk membatasi kerusakan lebih lanjut."
    elif abs_pnl >= 0.10:
        # Rugi sedang (10–20%): partial cut
        suggested = LossScenario.PARTIAL_CUT
        reason = f"Kerugian {abs_pnl*100:.1f}%. Partial cut mengurangi risiko sekaligus mempertahankan potensi recovery."
    else:
        # Rugi kecil (5–10%): stop loss atau hold
        suggested = LossScenario.STOP_LOSS
        reason = f"Kerugian {abs_pnl*100:.1f}% masih terkendali. Pasang stop loss untuk batasi risiko downside."

    return LossPositionAnalysis(
        canonical_symbol=pos.canonical_symbol,
        company_name=pos.company_name,
        shares=pos.shares,
        lots=pos.lots,
        avg_cost=pos.avg_cost,
        current_price=cp,
        total_cost=total_cost,
        market_value=mv,
        unrealized_pnl=round(pnl, 2),
        unrealized_pnl_pct=round(pnl_pct, 4),
        scenarios=scenarios,
        suggested_scenario=suggested,
        suggested_reason=reason,
    )
