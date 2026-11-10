"""
Portfolio Correlation Engine.

Menghitung matriks korelasi return harian antar instrumen dalam portofolio.
Pure function — tidak ada DB I/O.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class CorrelationPair:
    symbol_a: str
    symbol_b: str
    correlation: float          # -1.0 → +1.0
    interpretation: str         # STRONG_POSITIVE / MODERATE / UNCORRELATED / NEGATIVE


@dataclass
class CorrelationMatrix:
    symbols: list[str]
    matrix: dict[str, dict[str, float]]   # symbol → symbol → corr
    pairs: list[CorrelationPair]
    bars_used: int
    warnings: list[str]


def _interpret(corr: float) -> str:
    if corr >= 0.7:
        return "STRONG_POSITIVE"
    if corr >= 0.4:
        return "MODERATE_POSITIVE"
    if corr >= -0.4:
        return "UNCORRELATED"
    if corr >= -0.7:
        return "MODERATE_NEGATIVE"
    return "STRONG_NEGATIVE"


def compute_correlation_matrix(
    prices: dict[str, pd.Series],
    min_bars: int = 30,
) -> CorrelationMatrix:
    """
    Hitung matriks korelasi return harian.

    Args:
        prices: mapping symbol → Series harga penutupan (index = date)
        min_bars: minimum bar agar korelasi dianggap valid

    Returns:
        CorrelationMatrix dengan pasangan korelasi dan matrix penuh.
    """
    warnings: list[str] = []
    valid: dict[str, pd.Series] = {}

    for sym, s in prices.items():
        if len(s) < min_bars:
            warnings.append(f"{sym}: hanya {len(s)} bar, minimum {min_bars} — dilewati")
            continue
        returns = s.pct_change().dropna()
        if len(returns) < min_bars - 1:
            warnings.append(f"{sym}: return series terlalu pendek — dilewati")
            continue
        valid[sym] = returns

    if len(valid) < 2:
        return CorrelationMatrix(
            symbols=list(valid.keys()),
            matrix={},
            pairs=[],
            bars_used=0,
            warnings=warnings + ["Butuh minimal 2 instrumen dengan data cukup"],
        )

    df_returns = pd.DataFrame(valid)
    corr_df = df_returns.corr()
    bars_used = len(df_returns)

    symbols = list(corr_df.columns)
    matrix: dict[str, dict[str, float]] = {}
    pairs: list[CorrelationPair] = []

    for sym in symbols:
        matrix[sym] = {}
        for sym2 in symbols:
            val = float(corr_df.loc[sym, sym2])
            if pd.isna(val):
                val = 0.0
            matrix[sym][sym2] = round(val, 4)

    for i, sym_a in enumerate(symbols):
        for sym_b in symbols[i + 1:]:
            val = matrix[sym_a][sym_b]
            pairs.append(CorrelationPair(
                symbol_a=sym_a,
                symbol_b=sym_b,
                correlation=val,
                interpretation=_interpret(val),
            ))

    # Sort: korelasi paling tinggi dulu (absolute)
    pairs.sort(key=lambda p: abs(p.correlation), reverse=True)

    return CorrelationMatrix(
        symbols=symbols,
        matrix=matrix,
        pairs=pairs,
        bars_used=bars_used,
        warnings=warnings,
    )
