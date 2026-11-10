"""
Trade Feasibility Engine — R10.

Menjawab: "Kalau saya mau beli X saham, apakah itu realistis secara pasar?"

Checks:
  1. Lot size — IDX: 1 lot = 100 saham; US: 1 saham = 1 unit
  2. Capital adequacy — dana cukup untuk ≥ 1 lot + buffer spread
  3. ADV (Average Daily Volume) — order < 5% ADV (tidak menggerakkan pasar)
  4. Spread cost — estimasi biaya bid-ask sebagai % total cost
  5. Position limit — tidak melebihi IPS max_position_weight

Keamanan:
- TIDAK ADA eksekusi order. Ini hanya kalkulasi feasibility untuk riset.
- Semua angka dikembalikan untuk keputusan manusia — TIDAK ada auto-trade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# IDX Board Lot Rules (Bursa Efek Indonesia)
# ---------------------------------------------------------------------------

# IDX menggunakan sistem 3 papan:
#   Main Board & Development Board: 1 lot = 100 saham
#   Acceleration Board: 1 lot = 1 saham (tidak diimplementasi — jarang dipakai)
IDX_LOT_SIZE = 100
US_LOT_SIZE = 1   # US tidak ada minimum lot formal; 1 saham = 1 unit

# IDX tick size rules (Peraturan BEI No. II-A, berlaku sejak 2015)
# Harga saham → minimum pergerakan harga (tick)
_IDX_TICK_TABLE = [
    (200,     1),      # < Rp200          → tick Rp1
    (500,     2),      # Rp200 – <Rp500   → tick Rp2
    (2_000,   5),      # Rp500 – <Rp2.000 → tick Rp5
    (5_000,   10),     # Rp2.000 – <Rp5.000 → tick Rp10
    (float("inf"), 25),  # ≥ Rp5.000       → tick Rp25
]

# Estimasi spread sebagai jumlah tick (konservatif)
_IDX_TYPICAL_SPREAD_TICKS = 1
_US_TYPICAL_SPREAD_PCT = 0.0005  # 0.05% ≈ tipikal US large-cap


class FeasibilityStatus(str, Enum):
    FEASIBLE = "FEASIBLE"               # semua check lulus
    MARGINAL = "MARGINAL"               # ada peringatan, tapi masih bisa jalan
    NOT_FEASIBLE = "NOT_FEASIBLE"       # setidaknya 1 hard blocker


@dataclass
class FeasibilityCheck:
    name: str
    passed: bool
    is_hard_block: bool    # True = NOT_FEASIBLE jika gagal
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class TradeFeasibility:
    """
    Hasil kalkulasi feasibility untuk 1 trade potensial.
    TIDAK ada eksekusi order — hanya analisis untuk keputusan manusia.
    """
    status: FeasibilityStatus
    checks: list[FeasibilityCheck] = field(default_factory=list)

    # Angka yang dihitung
    lot_size: int = 100
    min_lots: int = 1
    min_cost_estimate: float = 0.0        # biaya minimum 1 lot (harga * lot_size)
    suggested_lots: Optional[int] = None  # lots yang dianjurkan sesuai IPS
    suggested_cost: Optional[float] = None
    adv_ratio: Optional[float] = None     # order_value / ADV_value
    spread_cost_pct: Optional[float] = None  # estimasi spread cost

    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tick size helper
# ---------------------------------------------------------------------------

def _get_tick_size(price: float) -> float:
    for threshold, tick in _IDX_TICK_TABLE:
        if price < threshold:
            return float(tick)
    return 25.0


def _estimate_spread_pct(price: float, exchange: str) -> float:
    if exchange == "IDX":
        tick = _get_tick_size(price)
        return (_IDX_TYPICAL_SPREAD_TICKS * tick) / price
    return _US_TYPICAL_SPREAD_PCT


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_trade_feasibility(
    *,
    exchange: str,                       # "IDX" atau "US"
    last_price: float,                   # harga terakhir
    available_cash: float,               # modal tersedia
    portfolio_total_value: float,        # nilai total portofolio
    portfolio_weight_current: float,     # bobot sektor/saham ini saat ini (0-1)
    max_position_weight: float,          # dari IPS
    adv_shares: Optional[float] = None,  # average daily volume (saham)
    desired_lots: Optional[int] = None,  # None = hitung sendiri
) -> TradeFeasibility:
    """
    Kalkulasi trade feasibility. TIDAK ada eksekusi order.

    Returns TradeFeasibility dengan status dan detail setiap check.
    """
    if last_price <= 0:
        return TradeFeasibility(
            status=FeasibilityStatus.NOT_FEASIBLE,
            blockers=["Harga saham tidak valid (≤ 0)"],
        )

    lot_size = IDX_LOT_SIZE if exchange == "IDX" else US_LOT_SIZE
    min_cost = last_price * lot_size
    checks: list[FeasibilityCheck] = []
    warnings: list[str] = []
    blockers: list[str] = []

    # ------------------------------------------------------------------
    # Check 1: Capital adequacy (1 lot minimum)
    # ------------------------------------------------------------------
    buffer = 1.03  # 3% buffer untuk komisi + spread
    capital_ok = available_cash >= min_cost * buffer
    checks.append(FeasibilityCheck(
        name="capital_min_lot",
        passed=capital_ok,
        is_hard_block=True,
        message=(
            f"Dana cukup untuk 1 lot ({min_cost:,.0f} + 3% buffer)"
            if capital_ok
            else f"Dana tidak cukup: perlu ≥ {min_cost * buffer:,.0f}, tersedia {available_cash:,.0f}"
        ),
        value=available_cash,
        threshold=min_cost * buffer,
    ))
    if not capital_ok:
        blockers.append(f"Dana tidak cukup untuk 1 lot (Rp{min_cost:,.0f} + 3% buffer)")

    # ------------------------------------------------------------------
    # Check 2: Position limit (IPS max_position_weight)
    # ------------------------------------------------------------------
    # Hitung berapa lots yang bisa dibeli tanpa melanggar batas posisi
    max_value_allowed = portfolio_total_value * max_position_weight
    current_position_value = portfolio_total_value * portfolio_weight_current
    headroom = max_value_allowed - current_position_value
    max_affordable_by_ips = max(0.0, headroom)

    max_lots_by_ips = int(max_affordable_by_ips / (last_price * lot_size)) if last_price > 0 else 0
    ips_ok = max_lots_by_ips >= 1

    checks.append(FeasibilityCheck(
        name="ips_position_limit",
        passed=ips_ok,
        is_hard_block=True,
        message=(
            f"IPS: masih bisa beli maks {max_lots_by_ips} lot (bobot maks {max_position_weight:.0%})"
            if ips_ok
            else f"IPS: posisi sudah di batas (bobot saat ini {portfolio_weight_current:.1%} ≥ maks {max_position_weight:.0%})"
        ),
        value=portfolio_weight_current,
        threshold=max_position_weight,
    ))
    if not ips_ok:
        blockers.append(f"Posisi sudah mencapai batas IPS ({max_position_weight:.0%})")

    # ------------------------------------------------------------------
    # Check 3: ADV liquidity check
    # ------------------------------------------------------------------
    adv_ratio: Optional[float] = None
    if adv_shares is not None and adv_shares > 0:
        order_lots = desired_lots or max(1, min(max_lots_by_ips, int(available_cash / min_cost)))
        order_shares = order_lots * lot_size
        adv_ratio = order_shares / adv_shares
        adv_ok = adv_ratio <= 0.05  # < 5% ADV
        adv_warn = not adv_ok and adv_ratio <= 0.25
        adv_extreme = adv_ratio > 0.25  # > 25% ADV → NOT_EXECUTABLE_AT_ASSUMED_SIZE

        checks.append(FeasibilityCheck(
            name="adv_liquidity",
            passed=adv_ok or adv_warn,
            is_hard_block=adv_extreme,
            message=(
                f"Order ≈ {adv_ratio:.1%} dari ADV — likuiditas OK"
                if adv_ok
                else (
                    f"Order ≈ {adv_ratio:.1%} dari ADV (>25%) — NOT_EXECUTABLE_AT_ASSUMED_SIZE"
                    if adv_extreme
                    else f"Order ≈ {adv_ratio:.1%} dari ADV — berisiko menggerakkan harga (maks 5%)"
                )
            ),
            value=adv_ratio,
            threshold=0.05,
        ))
        if adv_extreme:
            blockers.append(
                f"Order mencapai {adv_ratio:.1%} ADV (>25%) — tidak likuid pada ukuran asumsi (NOT_EXECUTABLE_AT_ASSUMED_SIZE)"
            )
            suggested_lots = None
            suggested_cost = None
        elif not adv_ok:
            warnings.append(f"Order mencapai {adv_ratio:.1%} ADV — pertimbangkan pecah order")
    elif adv_shares is not None and adv_shares <= 0:
        checks.append(FeasibilityCheck(
            name="adv_liquidity",
            passed=False,
            is_hard_block=True,
            message="ADV = 0 — saham tidak aktif diperdagangkan (NOT_EXECUTABLE_AT_ASSUMED_SIZE)",
            value=0.0,
            threshold=0.05,
        ))
        blockers.append("ADV = 0 — saham tidak likuid / tidak ada volume perdagangan")
    else:
        checks.append(FeasibilityCheck(
            name="adv_liquidity",
            passed=True,
            is_hard_block=False,
            message="Data ADV tidak tersedia — abaikan check likuiditas",
        ))

    # ------------------------------------------------------------------
    # Check 4: Spread cost estimate
    # ------------------------------------------------------------------
    spread_pct = _estimate_spread_pct(last_price, exchange)
    spread_ok = spread_pct <= 0.005  # < 0.5% spread cost
    checks.append(FeasibilityCheck(
        name="spread_cost",
        passed=spread_ok,
        is_hard_block=False,
        message=(
            f"Estimasi spread cost ≈ {spread_pct:.3%} — efisien"
            if spread_ok
            else f"Estimasi spread cost ≈ {spread_pct:.3%} — relatif tinggi untuk saham harga rendah"
        ),
        value=spread_pct,
        threshold=0.005,
    ))
    if not spread_ok:
        warnings.append(f"Spread cost ≈ {spread_pct:.3%} — saham harga sangat rendah berarti spread % lebih besar")

    # ------------------------------------------------------------------
    # Hitung suggested lots (lots optimal sesuai IPS + kapital)
    # ------------------------------------------------------------------
    if capital_ok and ips_ok:
        max_by_capital = int(available_cash / (min_cost * buffer))
        suggested_lots = min(max_by_capital, max_lots_by_ips)
        # Jika ada desired_lots, gunakan yang lebih kecil
        if desired_lots:
            suggested_lots = min(suggested_lots, desired_lots)
        suggested_lots = max(1, suggested_lots)
        suggested_cost = suggested_lots * min_cost
    else:
        suggested_lots = None
        suggested_cost = None

    # ------------------------------------------------------------------
    # Tentukan status keseluruhan
    # ------------------------------------------------------------------
    has_hard_block = any(not c.passed and c.is_hard_block for c in checks)
    has_warning = len(warnings) > 0

    if has_hard_block:
        status = FeasibilityStatus.NOT_FEASIBLE
    elif has_warning:
        status = FeasibilityStatus.MARGINAL
    else:
        status = FeasibilityStatus.FEASIBLE

    return TradeFeasibility(
        status=status,
        checks=checks,
        lot_size=lot_size,
        min_lots=1,
        min_cost_estimate=min_cost,
        suggested_lots=suggested_lots,
        suggested_cost=suggested_cost,
        adv_ratio=adv_ratio,
        spread_cost_pct=spread_pct,
        warnings=warnings,
        blockers=blockers,
    )
