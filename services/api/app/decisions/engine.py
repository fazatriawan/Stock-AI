"""
Rule-based recommendation engine — deterministik, tidak ada LLM di sini.
LLM hanya boleh membuat narasi, tidak boleh mengubah action/score dari engine ini.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

from app.analytics.fundamental import FundamentalSnapshot
from app.analytics.technical import TechnicalSnapshot


class Action(str, Enum):
    # Untuk posisi baru (tidak dimiliki)
    BUY = "BUY"              # sinyal beli kuat, kondisi terpenuhi
    WAIT = "WAIT"            # sinyal lemah / kondisi belum terpenuhi
    # Untuk posisi yang dimiliki
    ADD_CANDIDATE = "ADD_CANDIDATE"    # tambah posisi — tesis kuat, kapasitas ada
    HOLD = "HOLD"            # pertahankan
    TRIM_CANDIDATE = "TRIM_CANDIDATE"  # kurangi posisi — konsentrasi terlalu tinggi / tesis melemah
    SELL = "SELL"            # keluar — tesis patah
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Urgency(str, Enum):
    NORMAL = "NORMAL"
    REVIEW_NOW = "REVIEW_NOW"


class HardGateStatus(str, Enum):
    PASS = "PASS"
    FAIL_STALE_PRICE = "FAIL_STALE_PRICE"
    FAIL_NO_FUNDAMENTAL = "FAIL_NO_FUNDAMENTAL"
    FAIL_SUSPENSION = "FAIL_SUSPENSION"
    FAIL_COVERAGE = "FAIL_COVERAGE"
    FAIL_LIQUIDITY = "FAIL_LIQUIDITY"
    FAIL_CORPORATE_ACTION = "FAIL_CORPORATE_ACTION"


@dataclass
class PortfolioContext:
    owned: bool = False
    shares: float = 0.0
    cost_basis: float = 0.0
    portfolio_weight: float = 0.0  # current % of portfolio
    max_position_weight: float = 0.10  # config: maks 10% per saham
    available_cash: float = 0.0
    sector_weight: float = 0.0
    max_sector_weight: float = 0.30


@dataclass
class DecisionConfig:
    mode: str = "BALANCED"  # CONSERVATIVE / BALANCED / EXPLORATORY
    buy_score_threshold: float = 60.0
    # Coverage minimum dihitung dari core factors (fundamental+valuation+technical).
    # Macro/ownership/events tidak selalu tersedia — tidak memblokir analisis core.
    min_core_coverage: float = 0.60  # dari 3 core factors: fund+val+tech
    max_staleness_days: int = 3
    horizon: str = "3-12 months"


@dataclass
class FactorScores:
    fundamental: Optional[float] = None
    valuation: Optional[float] = None
    technical: Optional[float] = None
    macro_policy: Optional[float] = None
    risk_quality: Optional[float] = None
    events_news: Optional[float] = None
    ownership_flows: Optional[float] = None

    WEIGHTS = {
        "fundamental": 0.25,
        "valuation": 0.20,
        "technical": 0.15,
        "macro_policy": 0.15,
        "risk_quality": 0.15,
        "events_news": 0.05,
        "ownership_flows": 0.05,
    }

    def weighted_score(self) -> float:
        total_weight = 0.0
        total_score = 0.0
        for factor, weight in self.WEIGHTS.items():
            val = getattr(self, factor)
            if val is not None:
                total_score += val * weight
                total_weight += weight
        if total_weight == 0:
            return 0.0
        return total_score / total_weight * 100.0 / 100.0  # 0-100

    def coverage(self) -> float:
        available = sum(
            1 for f in self.WEIGHTS if getattr(self, f) is not None
        )
        return available / len(self.WEIGHTS)


@dataclass
class RecommendationOutput:
    instrument_id: str
    as_of: date
    action: Action
    urgency: Urgency
    horizon: str
    hard_gate_status: HardGateStatus
    hard_gate_reason: Optional[str]
    factor_scores: FactorScores
    composite_score: float
    evidence_confidence: str  # LOW / MEDIUM / HIGH
    owned: bool
    bull_thesis: list[str] = field(default_factory=list)
    bear_case: list[str] = field(default_factory=list)
    conditions_to_buy: list[str] = field(default_factory=list)
    conditions_to_sell: list[str] = field(default_factory=list)
    invalidation_triggers: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    changed_from: Optional[str] = None
    notes: str = ""
    rule_version: str = "v1.7.1"


def _score_technical(snap: TechnicalSnapshot) -> Optional[float]:
    """Hitung skor teknikal 0-100."""
    if not snap.sufficient_data:
        return None

    signals: list[tuple[float, float]] = []  # (weight, value 0-1)

    # Trend vs MA
    if snap.above_sma_20 is not None:
        signals.append((1.5, 1.0 if snap.above_sma_20 else 0.0))
    if snap.above_sma_50 is not None:
        signals.append((2.0, 1.0 if snap.above_sma_50 else 0.0))
    if snap.above_sma_200 is not None:
        signals.append((2.5, 1.0 if snap.above_sma_200 else 0.0))
    if snap.golden_cross is not None:
        signals.append((2.0, 1.0 if snap.golden_cross else 0.0))

    # RSI
    if snap.rsi_14 is not None:
        rsi = snap.rsi_14
        if 40 <= rsi <= 65:
            rsi_score = 0.7
        elif rsi < 30:
            rsi_score = 0.85  # oversold = peluang
        elif rsi > 75:
            rsi_score = 0.25  # overbought
        else:
            rsi_score = 0.5
        signals.append((1.5, rsi_score))

    # MACD momentum
    if snap.macd_hist is not None and snap.macd is not None:
        signals.append((1.0, 0.75 if snap.macd_hist > 0 else 0.25))

    # 52-week percentile
    if snap.percentile_52w is not None:
        p = snap.percentile_52w
        # sweet spot 30-70th percentile
        if 0.30 <= p <= 0.70:
            pct_score = 0.7
        elif p < 0.20:
            pct_score = 0.6  # near low
        elif p > 0.85:
            pct_score = 0.3  # near high
        else:
            pct_score = 0.5
        signals.append((1.0, pct_score))

    if not signals:
        return None

    total_w = sum(w for w, _ in signals)
    total_s = sum(w * v for w, v in signals)
    return min(100.0, max(0.0, (total_s / total_w) * 100.0))


def _score_fundamental(fund: FundamentalSnapshot, is_bank: bool) -> Optional[float]:
    """Skor fundamental 0-100 berdasarkan metrik yang tersedia."""
    scores: list[float] = []

    if is_bank:
        if fund.roe is not None:
            scores.append(min(100, max(0, (fund.roe - 0.08) / (0.22 - 0.08) * 100)))
        if fund.nim is not None:
            scores.append(min(100, max(0, (fund.nim - 0.03) / (0.08 - 0.03) * 100)))
        if fund.npl_gross is not None:
            # Lower NPL = better; invert
            scores.append(min(100, max(0, (0.05 - fund.npl_gross) / 0.05 * 100)))
        if fund.car is not None:
            scores.append(min(100, max(0, (fund.car - 0.14) / (0.25 - 0.14) * 100)))
    else:
        if fund.roe is not None:
            scores.append(min(100, max(0, (fund.roe - 0.05) / (0.25 - 0.05) * 100)))
        if fund.gross_margin is not None:
            scores.append(min(100, max(0, fund.gross_margin * 100)))
        if fund.operating_margin is not None:
            scores.append(min(100, max(0, fund.operating_margin * 100 * 2)))
        if fund.debt_to_equity is not None:
            # Lower = better
            scores.append(min(100, max(0, (3.0 - fund.debt_to_equity) / 3.0 * 100)))

    if not scores:
        return None
    return sum(scores) / len(scores)


def _score_valuation(fund: FundamentalSnapshot, is_bank: bool) -> Optional[float]:
    """Skor valuasi 0-100. Skor tinggi = murah secara relatif."""
    scores: list[float] = []

    if is_bank:
        if fund.pb_ratio is not None:
            # Bank: P/B 1-2x = wajar, <1 = murah, >3 = mahal
            pb = fund.pb_ratio
            if pb < 1.0:
                scores.append(80.0)
            elif pb <= 2.0:
                scores.append(65.0)
            elif pb <= 3.0:
                scores.append(45.0)
            else:
                scores.append(25.0)
    else:
        if fund.pe_ratio is not None and fund.pe_ratio > 0:
            pe = fund.pe_ratio
            if pe < 10:
                scores.append(80.0)
            elif pe < 15:
                scores.append(70.0)
            elif pe < 20:
                scores.append(55.0)
            elif pe < 30:
                scores.append(40.0)
            else:
                scores.append(20.0)

    if fund.dividend_yield is not None and fund.dividend_yield > 0:
        dy = fund.dividend_yield
        # Yield 3-6% = bagus, >8% mungkin distress
        if 0.03 <= dy <= 0.06:
            scores.append(75.0)
        elif dy > 0.06:
            scores.append(60.0)
        elif dy > 0.01:
            scores.append(50.0)

    if not scores:
        return None
    return sum(scores) / len(scores)


def run_decision_engine(
    instrument_id: str,
    as_of: date,
    technical: TechnicalSnapshot,
    fundamental: FundamentalSnapshot,
    portfolio: PortfolioContext,
    config: DecisionConfig,
    is_suspended: bool = False,
    has_unresolved_corporate_action: bool = False,
    stale_price: bool = False,
    previous_action: Optional[str] = None,
    last_price: Optional[float] = None,
    adv_shares: Optional[float] = None,
    exchange: str = "IDX",
) -> RecommendationOutput:
    """
    Pipeline rekomendasi deterministik.
    Urutan: hard gates → scoring → eligibility → action → output.
    """
    is_bank = fundamental.sector == "Financials"

    # --- Hard gates ---
    if is_suspended:
        return RecommendationOutput(
            instrument_id=instrument_id, as_of=as_of,
            action=Action.INSUFFICIENT_DATA, urgency=Urgency.REVIEW_NOW,
            horizon=config.horizon,
            hard_gate_status=HardGateStatus.FAIL_SUSPENSION,
            hard_gate_reason="Saham dalam status suspensi",
            factor_scores=FactorScores(), composite_score=0.0,
            evidence_confidence="LOW", owned=portfolio.owned,
            data_gaps=["suspension_status"],
        )

    if has_unresolved_corporate_action:
        return RecommendationOutput(
            instrument_id=instrument_id, as_of=as_of,
            action=Action.INSUFFICIENT_DATA, urgency=Urgency.REVIEW_NOW,
            horizon=config.horizon,
            hard_gate_status=HardGateStatus.FAIL_CORPORATE_ACTION,
            hard_gate_reason="Ada corporate action yang belum disesuaikan",
            factor_scores=FactorScores(), composite_score=0.0,
            evidence_confidence="LOW", owned=portfolio.owned,
            data_gaps=["corporate_action_adjustment"],
        )

    if stale_price:
        return RecommendationOutput(
            instrument_id=instrument_id, as_of=as_of,
            action=Action.INSUFFICIENT_DATA, urgency=Urgency.NORMAL,
            horizon=config.horizon,
            hard_gate_status=HardGateStatus.FAIL_STALE_PRICE,
            hard_gate_reason="Data harga terlalu lama, tidak dapat membuat rekomendasi",
            factor_scores=FactorScores(), composite_score=0.0,
            evidence_confidence="LOW", owned=portfolio.owned,
            data_gaps=["fresh_price_data"],
        )

    lot_size = 100 if exchange in ("IDX", "BEI") else 1
    if adv_shares is not None and (adv_shares <= 0 or (lot_size / adv_shares) > 0.25):
        return RecommendationOutput(
            instrument_id=instrument_id, as_of=as_of,
            action=Action.HOLD if portfolio.owned else Action.WAIT,
            urgency=Urgency.REVIEW_NOW if portfolio.owned else Urgency.NORMAL,
            horizon=config.horizon,
            hard_gate_status=HardGateStatus.FAIL_LIQUIDITY,
            hard_gate_reason="Likuiditas harian (ADV) terlalu tipis (>25% ADV untuk 1 lot) — NOT_EXECUTABLE_AT_ASSUMED_SIZE",
            factor_scores=FactorScores(), composite_score=0.0,
            evidence_confidence="LOW", owned=portfolio.owned,
            data_gaps=["liquidity_adv"],
        )

    # --- Scoring ---
    scores = FactorScores()
    scores.technical = _score_technical(technical)
    scores.fundamental = _score_fundamental(fundamental, is_bank)
    scores.valuation = _score_valuation(fundamental, is_bank)

    # Coverage dihitung dari 3 core factors saja (macro/ownership opsional)
    core_available = sum(
        1 for f in ("fundamental", "valuation", "technical")
        if getattr(scores, f) is not None
    )
    core_coverage = core_available / 3.0

    min_core = config.min_core_coverage
    if config.mode == "CONSERVATIVE":
        min_core = 0.80
    elif config.mode == "EXPLORATORY":
        min_core = 0.40

    if core_coverage < min_core:
        return RecommendationOutput(
            instrument_id=instrument_id, as_of=as_of,
            action=Action.INSUFFICIENT_DATA, urgency=Urgency.NORMAL,
            horizon=config.horizon,
            hard_gate_status=HardGateStatus.FAIL_COVERAGE,
            hard_gate_reason=f"Core coverage {core_coverage:.0%} < minimum {min_core:.0%}",
            factor_scores=scores, composite_score=0.0,
            evidence_confidence="LOW", owned=portfolio.owned,
            data_gaps=fundamental.metrics_missing + technical.missing_indicators,
        )

    composite = scores.weighted_score()

    # Evidence confidence
    if core_coverage >= 0.85 and len(fundamental.metrics_missing) <= 1:
        confidence = "HIGH"
    elif core_coverage >= 0.65:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # --- Eligibility rules ---
    data_gaps = fundamental.metrics_missing + technical.missing_indicators
    bull: list[str] = []
    bear: list[str] = []
    conditions_buy: list[str] = []
    conditions_sell: list[str] = []
    invalidation: list[str] = []

    # Build thesis bullets deterministik
    if scores.fundamental and scores.fundamental >= 65:
        bull.append("Kualitas bisnis di atas rata-rata peer berdasarkan metrik yang tersedia")
    if scores.valuation and scores.valuation >= 65:
        bull.append("Valuasi terlihat menarik secara historis/peer")
    if scores.technical and scores.technical >= 65:
        bull.append("Momentum teknikal mendukung tren positif")
    if technical.above_sma_200:
        bull.append("Harga di atas SMA200 — tren jangka panjang bullish")
    if technical.rsi_14 and technical.rsi_14 < 35:
        bull.append(f"RSI14={technical.rsi_14:.1f} menunjukkan area oversold potensial")

    if scores.valuation and scores.valuation < 40:
        bear.append("Valuasi dinilai mahal dibanding peer/historis")
    if scores.fundamental and scores.fundamental < 40:
        bear.append("Metrik fundamental di bawah rata-rata sektor")
    if technical.above_sma_200 is False:
        bear.append("Harga di bawah SMA200 — tren jangka panjang masih bearish")
    if technical.rsi_14 and technical.rsi_14 > 72:
        bear.append(f"RSI14={technical.rsi_14:.1f} masuk zona overbought")
    if fundamental.data_freshness == "STALE":
        bear.append("Data fundamental sudah cukup lama, perlu laporan terbaru")

    bear.extend([
        "Risiko makro dan kebijakan belum sepenuhnya terefleksi dalam data",
        "Perubahan manajemen, litigasi, atau event material tak terduga",
    ])

    invalidation = [
        "Laporan keuangan resmi menunjukkan penurunan metrik kunci secara signifikan",
        "Suspensi atau penyelidikan otoritas",
        "Perubahan material tesis bisnis inti",
    ]

    conditions_buy = [
        f"Skor komposit ≥ {config.buy_score_threshold:.0f} (saat ini {composite:.1f})",
        "Data fundamental Q terbaru tersedia dan terverifikasi",
        "Volume dan likuiditas memadai untuk ukuran posisi yang direncanakan",
    ]

    conditions_sell = [
        "Tesis utama terbukti salah berdasarkan data resmi",
        "Batas drawdown per posisi terlampaui",
        "Portofolio melebihi batas konsentrasi setelah rebalancing",
    ]

    # --- Determine action ---
    urgency = Urgency.NORMAL

    # Cek batas konsentrasi portfolio
    portfolio_risk_ok = (
        portfolio.portfolio_weight < portfolio.max_position_weight
        and portfolio.sector_weight < portfolio.max_sector_weight
    )

    if portfolio.owned:
        # Posisi yang sudah dimiliki — tentukan ADD/HOLD/TRIM/SELL
        thesis_intact = composite >= 45.0
        overweight = portfolio.portfolio_weight > portfolio.max_position_weight
        severely_overweight = portfolio.portfolio_weight > portfolio.max_position_weight * 1.2
        sector_overweight = portfolio.sector_weight > portfolio.max_sector_weight

        if overweight:
            urgency = Urgency.REVIEW_NOW

        if not thesis_intact:
            action = Action.SELL
        elif severely_overweight or sector_overweight:
            action = Action.TRIM_CANDIDATE
            urgency = Urgency.REVIEW_NOW
        elif overweight:
            action = Action.TRIM_CANDIDATE
        elif thesis_intact and composite >= config.buy_score_threshold and not overweight:
            # Tesis kuat DAN masih ada ruang — kandidat penambahan
            action = Action.ADD_CANDIDATE
        else:
            action = Action.HOLD
    else:
        # Kandidat baru — BUY atau WAIT
        quality_ok = (scores.fundamental or 0) >= 50 and (scores.valuation or 0) >= 45
        tech_ok = (scores.technical or 0) >= 45 if technical.sufficient_data else True
        score_ok = composite >= config.buy_score_threshold
        if last_price is not None and last_price > 0:
            min_lot_cost = last_price * lot_size * 1.03
            cash_ok = portfolio.available_cash >= min_lot_cost
            if not cash_ok:
                conditions_buy.append(
                    f"Modal tersedia (Rp{portfolio.available_cash:,.0f}) belum cukup untuk 1 lot minimum (Rp{min_lot_cost:,.0f})"
                )
        else:
            cash_ok = portfolio.available_cash > 0

        if quality_ok and tech_ok and score_ok and cash_ok and portfolio_risk_ok:
            action = Action.BUY
        else:
            action = Action.WAIT

    return RecommendationOutput(
        instrument_id=instrument_id,
        as_of=as_of,
        action=action,
        urgency=urgency,
        horizon=config.horizon,
        hard_gate_status=HardGateStatus.PASS,
        hard_gate_reason=None,
        factor_scores=scores,
        composite_score=composite,
        evidence_confidence=confidence,
        owned=portfolio.owned,
        bull_thesis=bull,
        bear_case=bear,
        conditions_to_buy=conditions_buy,
        conditions_to_sell=conditions_sell,
        invalidation_triggers=invalidation,
        data_gaps=data_gaps,
        changed_from=previous_action,
    )
