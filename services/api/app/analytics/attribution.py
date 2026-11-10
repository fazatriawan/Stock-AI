"""
HARD-05 (R18) — Decision & Portfolio Performance Attribution Engine.

Memisahkan variasi return posisi/keputusan menjadi:
1. Broad Market Effect (benchmark return, mis. IHSG / S&P 500)
2. Sector Effect (excess return sektor terhadap pasar)
3. Stock-Specific Alpha (seleksi emiten di luar pergerakan pasar & sektor)
4. Dividend Contribution (dividen kas bersih terhadap modal)
5. Transaction Cost Drag (beban komisi & pajak transaksi)

Catatan PRD §12 HARD-05:
Atribusi menjelaskan variasi historis yang teramati, BUKAN bukti kausalitas mutlak.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

DEFAULT_ATTRIBUTION_CAVEAT = (
    "Atribusi kinerja mendekomposisi variasi return yang teramati terhadap benchmark/sektor; "
    "angka ini bukan bukti kausalitas mutlak atau jaminan performa masa depan."
)


@dataclass
class PositionAttributionInput:
    symbol: str
    sector: Optional[str]
    total_cost: float                          # total biaya termasuk fee + tax
    gross_cost: float                          # shares * harga beli (tanpa fee/tax)
    market_value: float                        # nilai pasar saat ini
    dividend_received: float = 0.0             # dividen kas bersih yang diterima
    benchmark_return_pct: float = 0.0          # return indeks acuan (%) pada periode sama
    sector_return_pct: Optional[float] = None  # return rata-rata sektor (%) pada periode sama


@dataclass
class PositionAttributionResult:
    symbol: str
    sector: Optional[str]
    weight: float
    total_return_pct: float
    price_return_pct: float
    dividend_contribution_pct: float
    cost_drag_pct: float
    benchmark_effect_pct: float
    sector_excess_pct: float
    stock_specific_alpha_pct: float
    baseline_excess_pct: float
    attribution_caveat: str = DEFAULT_ATTRIBUTION_CAVEAT


@dataclass
class PortfolioAttributionReport:
    portfolio_total_return_pct: float
    benchmark_return_pct: float
    portfolio_excess_return_pct: float
    weighted_sector_effect_pct: float
    weighted_stock_alpha_pct: float
    weighted_dividend_pct: float
    weighted_cost_drag_pct: float
    positions: list[PositionAttributionResult] = field(default_factory=list)
    caveat: str = DEFAULT_ATTRIBUTION_CAVEAT


def compute_position_attribution(
    inp: PositionAttributionInput,
    weight: float = 1.0,
) -> PositionAttributionResult:
    """Hitung dekomposisi return untuk satu posisi saham."""
    if inp.total_cost <= 0 or inp.gross_cost <= 0:
        return PositionAttributionResult(
            symbol=inp.symbol,
            sector=inp.sector,
            weight=round(weight, 4),
            total_return_pct=0.0,
            price_return_pct=0.0,
            dividend_contribution_pct=0.0,
            cost_drag_pct=0.0,
            benchmark_effect_pct=round(inp.benchmark_return_pct, 2),
            sector_excess_pct=0.0,
            stock_specific_alpha_pct=0.0,
            baseline_excess_pct=round(-inp.benchmark_return_pct, 2),
        )

    # Gross price return (sebelum fee/tax)
    gross_price_return_pct = ((inp.market_value - inp.gross_cost) / inp.gross_cost) * 100.0
    # Net price return (setelah fee/tax masuk ke total_cost)
    net_price_return_pct = ((inp.market_value - inp.total_cost) / inp.total_cost) * 100.0
    # Cost drag (selalu <= 0 jika total_cost >= gross_cost)
    cost_drag_pct = net_price_return_pct - gross_price_return_pct
    # Dividend contribution terhadap total_cost
    dividend_pct = (inp.dividend_received / inp.total_cost) * 100.0
    # Total return net (price + dividend)
    total_return_pct = net_price_return_pct + dividend_pct

    benchmark_pct = inp.benchmark_return_pct
    sector_ref_pct = inp.sector_return_pct if inp.sector_return_pct is not None else benchmark_pct
    sector_excess_pct = sector_ref_pct - benchmark_pct

    # Stock-specific alpha (gross price return dibanding sektor)
    stock_alpha_pct = gross_price_return_pct - sector_ref_pct
    baseline_excess_pct = total_return_pct - benchmark_pct

    return PositionAttributionResult(
        symbol=inp.symbol,
        sector=inp.sector,
        weight=round(weight, 4),
        total_return_pct=round(total_return_pct, 2),
        price_return_pct=round(net_price_return_pct, 2),
        dividend_contribution_pct=round(dividend_pct, 2),
        cost_drag_pct=round(cost_drag_pct, 2),
        benchmark_effect_pct=round(benchmark_pct, 2),
        sector_excess_pct=round(sector_excess_pct, 2),
        stock_specific_alpha_pct=round(stock_alpha_pct, 2),
        baseline_excess_pct=round(baseline_excess_pct, 2),
    )


def compute_portfolio_attribution(
    inputs: list[PositionAttributionInput],
    benchmark_return_pct: float = 0.0,
) -> PortfolioAttributionReport:
    """Hitung atribusi kinerja di tingkat portofolio beserta rincian per saham."""
    if not inputs:
        return PortfolioAttributionReport(
            portfolio_total_return_pct=0.0,
            benchmark_return_pct=round(benchmark_return_pct, 2),
            portfolio_excess_return_pct=round(-benchmark_return_pct, 2),
            weighted_sector_effect_pct=0.0,
            weighted_stock_alpha_pct=0.0,
            weighted_dividend_pct=0.0,
            weighted_cost_drag_pct=0.0,
            positions=[],
        )

    total_cost_all = sum(max(0.0, item.total_cost) for item in inputs)
    if total_cost_all <= 0:
        weights = [1.0 / len(inputs)] * len(inputs)
    else:
        weights = [max(0.0, item.total_cost) / total_cost_all for item in inputs]

    pos_results: list[PositionAttributionResult] = []
    for item, w in zip(inputs, weights):
        pos_results.append(compute_position_attribution(item, weight=w))

    port_total_return = sum(p.total_return_pct * p.weight for p in pos_results)
    weighted_sector = sum(p.sector_excess_pct * p.weight for p in pos_results)
    weighted_alpha = sum(p.stock_specific_alpha_pct * p.weight for p in pos_results)
    weighted_div = sum(p.dividend_contribution_pct * p.weight for p in pos_results)
    weighted_cost = sum(p.cost_drag_pct * p.weight for p in pos_results)

    return PortfolioAttributionReport(
        portfolio_total_return_pct=round(port_total_return, 2),
        benchmark_return_pct=round(benchmark_return_pct, 2),
        portfolio_excess_return_pct=round(port_total_return - benchmark_return_pct, 2),
        weighted_sector_effect_pct=round(weighted_sector, 2),
        weighted_stock_alpha_pct=round(weighted_alpha, 2),
        weighted_dividend_pct=round(weighted_div, 2),
        weighted_cost_drag_pct=round(weighted_cost, 2),
        positions=pos_results,
    )
