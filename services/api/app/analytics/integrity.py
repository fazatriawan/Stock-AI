"""
Financial Integrity Checker — PRD §DATA-06 / HARD-04.

Memvalidasi konsistensi cross-field pada FinancialFact sebelum dipakai engine.
Tidak mengubah data sumber — hanya menandai konflik dan metrik yang tidak bisa dipercaya.

Ketidaksesuaian material → INCONSISTENT / BLOCKED.
Jangan pernah "memaksa balance" dengan mengubah angka sumber.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from app.db.models import FinancialFact, Instrument


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class IntegrityFlag(str, Enum):
    OK = "OK"
    INCONSISTENT = "INCONSISTENT"       # cross-field mismatch melebihi toleransi
    BOUNDS_VIOLATION = "BOUNDS_VIOLATION"  # nilai di luar rentang wajar
    PERIOD_DUPLICATE = "PERIOD_DUPLICATE"  # dua record untuk periode yang sama
    SIGN_CONTRADICTION = "SIGN_CONTRADICTION"  # arah nilai bertentangan secara logis
    UNIT_SUSPECT = "UNIT_SUSPECT"       # skala nilai tidak masuk akal


@dataclass
class MetricConflict:
    metric: str
    flag: IntegrityFlag
    value: Optional[float]
    description: str
    affected_downstream: list[str] = field(default_factory=list)


@dataclass
class IntegrityReport:
    instrument_id: str
    canonical_symbol: str
    checked_at: datetime
    facts_checked: int
    conflicts: list[MetricConflict]
    blocked_metrics: list[str]  # metrik yang harus diperlakukan sebagai INSUFFICIENT_DATA
    overall_status: str  # "CLEAN" | "WARNINGS" | "BLOCKED"

    @property
    def has_blocks(self) -> bool:
        return bool(self.blocked_metrics)

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)


# ---------------------------------------------------------------------------
# Bounds per metrik
# ---------------------------------------------------------------------------

# (min_value, max_value, is_blocking)
# is_blocking=True → metrik diblokir jika di luar batas
METRIC_BOUNDS: dict[str, tuple[float, float, bool]] = {
    "PE_RATIO":        (-500.0,  2000.0, False),  # PE negatif valid (rugi); > 2000 aneh
    "P/B":             (-10.0,   200.0,  False),  # PB negatif bisa terjadi; > 200 sangat aneh
    "ROE":             (-5.0,    10.0,   False),  # ROE > 1000% perlu diaudit
    "GROSS_MARGIN":    (-1.0,    1.0,    True),   # margin di luar [-100%, 100%] adalah error
    "OPERATING_MARGIN":(-2.0,   1.0,    True),   # opex bisa besar tapi tidak mungkin > 100%
    "NET_MARGIN":      (-2.0,   1.0,    True),
    "DIVIDEND_YIELD":  (0.0,   50.0,    False),  # tersimpan dalam format persen (7.87 = 7.87%); > 50% tidak wajar
    "DEBT_TO_EQUITY":  (-5.0,   50.0,   False),  # D/E negatif bisa (ekuitas negatif)
    "BETA":            (-3.0,   5.0,    False),
    "NIM":             (-0.1,   0.5,    False),  # NIM bank: [-10%, 50%]
    "NPL_GROSS":       (0.0,    1.0,    False),  # NPL 0–100%
    "CAR":             (0.0,    1.0,    False),  # CAR 0–100%
    "LDR":             (0.0,    2.0,    False),  # LDR bisa > 100%
}

# Metrik yang harus ikut di-block kalau metrik kunci error
DOWNSTREAM_DEPS: dict[str, list[str]] = {
    "EPS_TRAILING": ["PE_RATIO"],
    "EPS":          ["PE_RATIO"],
    "NET_INCOME":   ["ROE", "NET_MARGIN", "EPS"],
    "GROSS_MARGIN": ["OPERATING_MARGIN", "NET_MARGIN"],
    "PE_RATIO":     [],
    "P/B":          [],
    "ROE":          [],
}


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_bounds(
    metric: str,
    value: float,
) -> Optional[MetricConflict]:
    """Periksa apakah nilai metrik dalam rentang yang wajar."""
    bounds = METRIC_BOUNDS.get(metric)
    if bounds is None:
        return None
    lo, hi, is_blocking = bounds
    if not (lo <= value <= hi):
        flag = IntegrityFlag.BOUNDS_VIOLATION
        downstream = DOWNSTREAM_DEPS.get(metric, [])
        return MetricConflict(
            metric=metric,
            flag=flag,
            value=value,
            description=(
                f"{metric} = {value:.4f} di luar rentang wajar [{lo}, {hi}]. "
                "Periksa satuan atau revisi data sumber."
            ),
            affected_downstream=downstream if is_blocking else [],
        )
    return None


def _check_pe_eps_sign(
    pe: Optional[float],
    eps: Optional[float],
) -> Optional[MetricConflict]:
    """
    PE positif mengimplikasikan EPS positif (perusahaan untung).
    Kontradiksi PE > 0 & EPS < 0 adalah error — bukan kondisi yang bisa terjadi secara akuntansi.
    """
    if pe is None or eps is None:
        return None
    if pe > 0 and eps < 0:
        return MetricConflict(
            metric="PE_RATIO",
            flag=IntegrityFlag.SIGN_CONTRADICTION,
            value=pe,
            description=(
                f"PE_RATIO = {pe:.2f} (positif) tetapi EPS = {eps:.4f} (negatif). "
                "PE > 0 hanya valid jika perusahaan untung. "
                "Periksa definisi EPS yang dipakai (trailing vs forward)."
            ),
            affected_downstream=["PE_RATIO"],
        )
    if pe < 0 and eps > 0:
        return MetricConflict(
            metric="PE_RATIO",
            flag=IntegrityFlag.SIGN_CONTRADICTION,
            value=pe,
            description=(
                f"PE_RATIO = {pe:.2f} (negatif) tetapi EPS = {eps:.4f} (positif). "
                "Periksa apakah PE dihitung dari metrik yang berbeda dengan EPS yang tersedia."
            ),
            affected_downstream=["PE_RATIO"],
        )
    return None


def _check_pe_market_cap_net_income(
    pe: Optional[float],
    market_cap: Optional[float],
    net_income: Optional[float],
    tolerance: float = 0.25,
) -> Optional[MetricConflict]:
    """
    PE ≈ MARKET_CAP / NET_INCOME.
    Toleransi 25% — definisi PE bervariasi (diluted, basic, adjusted).
    Hanya cek jika ketiga nilai tersedia dan positif.
    """
    if pe is None or market_cap is None or net_income is None:
        return None
    if net_income <= 0 or market_cap <= 0 or pe <= 0:
        return None

    pe_derived = market_cap / net_income
    deviation = abs(pe - pe_derived) / max(abs(pe_derived), 1e-9)

    if deviation > tolerance:
        return MetricConflict(
            metric="PE_RATIO",
            flag=IntegrityFlag.INCONSISTENT,
            value=pe,
            description=(
                f"PE_RATIO = {pe:.2f} tidak konsisten dengan "
                f"MARKET_CAP / NET_INCOME = {pe_derived:.2f} "
                f"(deviasi {deviation * 100:.1f}%, toleransi {tolerance * 100:.0f}%). "
                "Kemungkinan perbedaan definisi share count atau adj. earnings."
            ),
            affected_downstream=[],
        )
    return None


def _check_margin_net_income_sign(
    gross_margin: Optional[float],
    net_income: Optional[float],
) -> Optional[MetricConflict]:
    """
    Gross margin negatif → perusahaan menjual di bawah HPP.
    Sangat tidak biasa untuk perusahaan IDX yang beroperasi normal.
    Net income < 0 dengan gross margin positif adalah wajar (tingginya opex/biaya keuangan).
    Net income < 0 dengan gross margin < 0 → double red flag.
    """
    if gross_margin is None or net_income is None:
        return None
    if gross_margin < 0 and net_income < 0:
        return MetricConflict(
            metric="GROSS_MARGIN",
            flag=IntegrityFlag.INCONSISTENT,
            value=gross_margin,
            description=(
                f"GROSS_MARGIN = {gross_margin:.4f} dan NET_INCOME = {net_income:.2f} "
                "keduanya negatif. Periksa apakah ini benar atau ada error satuan."
            ),
            affected_downstream=["GROSS_MARGIN", "OPERATING_MARGIN"],
        )
    return None


def _check_period_duplicates(
    facts: list[FinancialFact],
) -> list[MetricConflict]:
    """Deteksi dua fact dengan metric dan period_end yang sama."""
    seen: dict[tuple[str, date], list[FinancialFact]] = {}
    for fact in facts:
        key = (fact.metric.upper(), fact.period_end)
        seen.setdefault(key, []).append(fact)

    conflicts: list[MetricConflict] = []
    for (metric, period_end), dups in seen.items():
        if len(dups) > 1:
            vals = [str(d.value) for d in dups]
            conflicts.append(MetricConflict(
                metric=metric,
                flag=IntegrityFlag.PERIOD_DUPLICATE,
                value=None,
                description=(
                    f"{metric} periode {period_end.isoformat()} muncul {len(dups)} kali "
                    f"(nilai: {', '.join(vals)}). Gunakan nilai yang paling baru atau dari sumber primer."
                ),
                affected_downstream=[metric],
            ))
    return conflicts


def _check_idr_unit_reasonableness(
    metric: str,
    value: float,
    currency: Optional[str],
    exchange: str,
) -> Optional[MetricConflict]:
    """
    Untuk saham IDX (IDR), beberapa metrik punya rentang wajar.
    EPS per saham IDX: biasanya Rp10 – Rp10.000 per lembar.
    Jika EPS > 1.000.000 untuk saham IDR, kemungkinan satuan salah (dalam jutaan, bukan per lembar).
    """
    if exchange not in ("IDX", "BEI") and currency != "IDR":
        return None

    if metric in ("EPS_TRAILING", "EPS_FORWARD", "EPS"):
        if value > 1_000_000:
            return MetricConflict(
                metric=metric,
                flag=IntegrityFlag.UNIT_SUSPECT,
                value=value,
                description=(
                    f"{metric} = {value:,.0f} IDR/saham sangat besar untuk saham IDX. "
                    "Kemungkinan satuan seharusnya IDR/saham tetapi data dalam jutaan IDR. "
                    "Periksa normalisasi satuan dari provider."
                ),
                affected_downstream=["PE_RATIO"],
            )
    return None


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def run_integrity_check(
    instrument: Instrument,
    facts: list[FinancialFact],
) -> IntegrityReport:
    """
    Jalankan semua integrity checks terhadap kumpulan FinancialFact.
    Tidak mengubah data sumber — hanya melaporkan konflik.
    """
    conflicts: list[MetricConflict] = []
    checked_at = datetime.now(tz=timezone.utc)

    # Bangun lookup metric → nilai terbaru
    metric_values: dict[str, float] = {}
    metric_currencies: dict[str, Optional[str]] = {}
    for fact in facts:
        m = fact.metric.upper()
        if m not in metric_values and fact.value is not None:
            metric_values[m] = float(fact.value)
            metric_currencies[m] = fact.currency

    # 1. Bounds check per metrik
    for metric, value in metric_values.items():
        conflict = _check_bounds(metric, value)
        if conflict:
            conflicts.append(conflict)

    # 2. PE/EPS sign consistency
    pe = metric_values.get("PE_RATIO")
    eps = metric_values.get("EPS_TRAILING") or metric_values.get("EPS")
    conflict = _check_pe_eps_sign(pe, eps)
    if conflict:
        conflicts.append(conflict)

    # 3. PE vs MARKET_CAP / NET_INCOME
    conflict = _check_pe_market_cap_net_income(
        pe,
        metric_values.get("MARKET_CAP"),
        metric_values.get("NET_INCOME"),
    )
    if conflict:
        conflicts.append(conflict)

    # 4. Gross margin + net income sign
    conflict = _check_margin_net_income_sign(
        metric_values.get("GROSS_MARGIN"),
        metric_values.get("NET_INCOME"),
    )
    if conflict:
        conflicts.append(conflict)

    # 5. Period duplicates
    dup_conflicts = _check_period_duplicates(facts)
    conflicts.extend(dup_conflicts)

    # 6. IDR unit reasonableness
    for metric, value in metric_values.items():
        currency = metric_currencies.get(metric)
        conflict = _check_idr_unit_reasonableness(metric, value, currency, instrument.exchange)
        if conflict:
            conflicts.append(conflict)

    # Kumpulkan blocked metrics (semua affected_downstream dari konflik)
    blocked: set[str] = set()
    for c in conflicts:
        blocked.update(c.affected_downstream)

    # Tentukan overall status
    if not conflicts:
        status = "CLEAN"
    elif blocked:
        status = "BLOCKED"
    else:
        status = "WARNINGS"

    return IntegrityReport(
        instrument_id=instrument.id,
        canonical_symbol=instrument.canonical_symbol,
        checked_at=checked_at,
        facts_checked=len(facts),
        conflicts=conflicts,
        blocked_metrics=sorted(blocked),
        overall_status=status,
    )
