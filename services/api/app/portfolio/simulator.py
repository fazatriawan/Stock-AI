"""
Capital allocation & rebalance simulator — Phase 4.

Semua kalkulasi hipotetis — tidak ada transaksi nyata.
Pengguna wajib mengkonfirmasi sebelum mengeksekusi apapun.
Disclaimer: bukan nasihat investasi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.portfolio.calculator import PositionData


# ---------------------------------------------------------------------------
# Target weight advisor
# ---------------------------------------------------------------------------

@dataclass
class TargetAllocation:
    canonical_symbol: str
    company_name: Optional[str]
    sector: Optional[str]
    current_shares: float
    current_lots: float
    current_weight: float       # bobot portofolio saat ini
    target_weight: float        # bobot yang diinginkan
    current_market_value: float
    target_market_value: float  # berdasarkan target weight & total portfolio
    delta_value: float          # target_mv - current_mv (positif = beli, negatif = jual)
    delta_lots: float           # lot yang perlu dibeli/dijual (dibulatkan ke 1 lot)
    action: str                 # BUY / SELL / HOLD
    note: str


@dataclass
class RebalanceSimulation:
    """Simulasi rebalancing ke target bobot."""
    total_portfolio_value: float
    positions_count: int
    allocations: list[TargetAllocation]
    # Ringkasan aksi
    buy_actions: int
    sell_actions: int
    hold_actions: int
    total_buy_value: float
    total_sell_value: float
    net_cash_needed: float   # positif = butuh modal tambahan, negatif = ada sisa kas
    disclaimer: str = (
        "Simulasi ini bersifat hipotetis dan hanya untuk keperluan perencanaan. "
        "Tidak ada transaksi nyata yang terjadi. Keputusan rebalancing sepenuhnya "
        "menjadi tanggung jawab pengguna."
    )


# ---------------------------------------------------------------------------
# New capital allocation advisor
# ---------------------------------------------------------------------------

@dataclass
class AllocationSuggestion:
    canonical_symbol: str
    company_name: Optional[str]
    sector: Optional[str]
    current_weight: float
    suggested_new_amount: float   # IDR yang disarankan untuk diinvestasikan
    suggested_lots: float         # lot (dibulatkan ke bawah)
    rationale: str
    priority: int                 # 1 = highest


@dataclass
class CapitalAllocationPlan:
    """Rencana alokasi modal baru ke portofolio yang sudah ada."""
    new_capital: float
    total_positions: int
    suggestions: list[AllocationSuggestion]
    undiversified_warning: Optional[str]
    disclaimer: str = (
        "Saran alokasi dihitung berdasarkan underweight posisi saat ini. "
        "Ini bukan rekomendasi beli/jual. Keputusan investasi sepenuhnya tanggung jawab pengguna."
    )


# ---------------------------------------------------------------------------
# Simulasi rebalancing
# ---------------------------------------------------------------------------

LOT_SIZE = 100


def simulate_rebalance(
    positions: dict[str, PositionData],
    target_weights: dict[str, float],  # {canonical_symbol: target_weight (0–1)}
    new_capital: float = 0.0,
) -> RebalanceSimulation:
    """
    Simulasi rebalancing ke bobot target.

    Args:
        positions: posisi saat ini (sudah enriched dengan harga)
        target_weights: {canonical_symbol: target_weight} — tidak harus sum=1
        new_capital: modal tambahan yang tersedia (opsional)
    """
    total_mv = sum(
        p.market_value for p in positions.values() if p.market_value is not None
    )
    total_cost_fallback = sum(p.total_cost for p in positions.values())
    total_value = (total_mv if total_mv > 0 else total_cost_fallback) + new_capital

    # Normalise target weights — jika user menentukan sebagian, sisanya dibagi rata
    specified_symbols = set(target_weights.keys())
    total_specified_weight = sum(target_weights.values())

    # Buat mapping symbol → position
    sym_to_pos: dict[str, PositionData] = {
        p.canonical_symbol: p for p in positions.values()
    }

    allocations: list[TargetAllocation] = []
    buy_actions = sell_actions = hold_actions = 0
    total_buy = total_sell = 0.0

    for sym, pos in sym_to_pos.items():
        t_weight = target_weights.get(sym, pos.current_weight if hasattr(pos, 'current_weight') else pos.weight)
        # fallback: pakai weight saat ini jika tidak ada target
        if sym not in target_weights:
            t_weight = pos.weight

        current_mv = pos.market_value if pos.market_value is not None else pos.total_cost
        target_mv = total_value * t_weight
        delta = target_mv - current_mv

        # Hitung lot
        current_price = pos.current_price or pos.avg_cost
        if current_price > 0 and abs(delta) >= current_price * LOT_SIZE:
            raw_lots = delta / (current_price * LOT_SIZE)
            # Bulatkan: beli → floor, jual → ceil (konservatif)
            import math
            delta_lots = math.floor(raw_lots) if delta > 0 else math.ceil(raw_lots)
        else:
            delta_lots = 0

        if delta_lots > 0:
            action = "BUY"
            note = f"Tambah {delta_lots} lot untuk mencapai bobot {t_weight*100:.1f}%"
            buy_actions += 1
            total_buy += abs(delta_lots) * LOT_SIZE * current_price
        elif delta_lots < 0:
            action = "SELL"
            note = f"Kurangi {abs(delta_lots)} lot — bobot saat ini {pos.weight*100:.1f}% > target {t_weight*100:.1f}%"
            sell_actions += 1
            total_sell += abs(delta_lots) * LOT_SIZE * current_price
        else:
            action = "HOLD"
            note = f"Bobot saat ini {pos.weight*100:.1f}% sudah mendekati target {t_weight*100:.1f}%"
            hold_actions += 1

        allocations.append(TargetAllocation(
            canonical_symbol=sym,
            company_name=pos.company_name,
            sector=pos.sector,
            current_shares=pos.shares,
            current_lots=pos.lots,
            current_weight=pos.weight,
            target_weight=t_weight,
            current_market_value=current_mv,
            target_market_value=round(target_mv, 2),
            delta_value=round(delta, 2),
            delta_lots=delta_lots,
            action=action,
            note=note,
        ))

    # Sort: SELL dulu, lalu BUY, lalu HOLD
    order = {"SELL": 0, "BUY": 1, "HOLD": 2}
    allocations.sort(key=lambda a: (order[a.action], -abs(a.delta_value)))

    net_cash = total_sell - total_buy + new_capital

    return RebalanceSimulation(
        total_portfolio_value=round(total_value, 2),
        positions_count=len(positions),
        allocations=allocations,
        buy_actions=buy_actions,
        sell_actions=sell_actions,
        hold_actions=hold_actions,
        total_buy_value=round(total_buy, 2),
        total_sell_value=round(total_sell, 2),
        net_cash_needed=round(-net_cash, 2),
    )


def plan_new_capital(
    positions: dict[str, PositionData],
    new_capital: float,
    max_position_weight: float = 0.25,
) -> CapitalAllocationPlan:
    """
    Tentukan cara terbaik mengalokasikan modal baru ke portofolio existing.

    Strategi: prioritaskan posisi yang underweight, hindari menambah yang sudah overweight.
    """
    total_mv = sum(p.market_value for p in positions.values() if p.market_value is not None)
    total_cost = sum(p.total_cost for p in positions.values())
    total_value = (total_mv if total_mv > 0 else total_cost) + new_capital

    if total_value <= 0 or not positions:
        return CapitalAllocationPlan(
            new_capital=new_capital,
            total_positions=0,
            suggestions=[],
            undiversified_warning="Portofolio kosong",
        )

    # Kalkulasi underweight per posisi
    suggestions: list[AllocationSuggestion] = []

    # Hitung equal-weight ideal
    n = len(positions)
    equal_weight = 1.0 / n if n > 0 else 0.0

    for pos in positions.values():
        current_weight_in_new_total = (
            (pos.market_value or pos.total_cost) / total_value
        )

        # Skipping positions yang sudah overweight
        if current_weight_in_new_total >= max_position_weight:
            continue

        # Underweight = berapa persen di bawah equal weight
        gap = equal_weight - current_weight_in_new_total
        if gap <= 0:
            continue

        # Alokasi proporsional ke gap
        suggested_amount = new_capital * (gap / sum(
            max(0, equal_weight - (p.market_value or p.total_cost) / total_value)
            for p in positions.values()
            if (p.market_value or p.total_cost) / total_value < max_position_weight
        )) if any(
            (p.market_value or p.total_cost) / total_value < max_position_weight
            for p in positions.values()
        ) else 0.0

        current_price = pos.current_price or pos.avg_cost
        if current_price <= 0:
            continue

        import math
        suggested_lots = math.floor(suggested_amount / (current_price * LOT_SIZE))
        if suggested_lots < 1:
            continue

        rationale = (
            f"Bobot saat ini {current_weight_in_new_total*100:.1f}% < "
            f"equal-weight ideal {equal_weight*100:.1f}%"
        )

        suggestions.append(AllocationSuggestion(
            canonical_symbol=pos.canonical_symbol,
            company_name=pos.company_name,
            sector=pos.sector,
            current_weight=pos.weight,
            suggested_new_amount=round(suggested_lots * LOT_SIZE * current_price, 0),
            suggested_lots=suggested_lots,
            rationale=rationale,
            priority=0,
        ))

    # Sort by gap terbesar (underweight terbesar) = prioritas lebih tinggi
    suggestions.sort(key=lambda s: s.current_weight)
    for i, s in enumerate(suggestions):
        s.priority = i + 1

    warning = None
    if n < 5:
        warning = f"Hanya {n} posisi — pertimbangkan diversifikasi ke saham/sektor lain"

    return CapitalAllocationPlan(
        new_capital=new_capital,
        total_positions=n,
        suggestions=suggestions,
        undiversified_warning=warning,
    )
