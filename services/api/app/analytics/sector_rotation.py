"""
Sector Rotation Tracker.

Menganalisis momentum return sektoral untuk mendeteksi rotasi kapital
antar sektor IDX / US. Pure function — tidak ada DB I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class SectorMomentum:
    sector: str
    return_1w: Optional[float]    # % 1 minggu
    return_1m: Optional[float]    # % 1 bulan
    return_3m: Optional[float]    # % 3 bulan
    momentum_score: float          # skor komposit -100 → +100
    signal: str                    # ACCUMULATE / NEUTRAL / DISTRIBUTE


@dataclass
class RotationReport:
    top_sectors: list[SectorMomentum]     # urutan momentum tertinggi
    bottom_sectors: list[SectorMomentum]  # urutan momentum terendah
    all_sectors: list[SectorMomentum]
    rotation_detected: bool
    rotation_note: str
    as_of: Optional[str] = None


def _momentum_score(r1w: Optional[float], r1m: Optional[float], r3m: Optional[float]) -> float:
    """Weighted score: 1W=30%, 1M=40%, 3M=30%."""
    score = 0.0
    weight = 0.0
    if r1w is not None:
        score += r1w * 0.30
        weight += 0.30
    if r1m is not None:
        score += r1m * 0.40
        weight += 0.40
    if r3m is not None:
        score += r3m * 0.30
        weight += 0.30
    return round(score / weight, 2) if weight > 0 else 0.0


def _signal(score: float) -> str:
    if score >= 3.0:
        return "ACCUMULATE"
    if score <= -3.0:
        return "DISTRIBUTE"
    return "NEUTRAL"


def compute_sector_rotation(
    sector_prices: dict[str, pd.Series],
) -> RotationReport:
    """
    Hitung momentum sektoral dari time-series harga (atau indeks) per sektor.

    Args:
        sector_prices: mapping sector_name → Series harga dengan index date.
                       Bisa berupa indeks sektoral atau rata-rata harga saham dalam sektor.
    Returns:
        RotationReport dengan ranking sektor berdasarkan momentum.
    """
    if not sector_prices:
        return RotationReport(
            top_sectors=[], bottom_sectors=[], all_sectors=[],
            rotation_detected=False,
            rotation_note="Tidak ada data sektor",
        )

    results: list[SectorMomentum] = []
    as_of_date: Optional[str] = None

    for sector, series in sector_prices.items():
        if len(series) < 5:
            continue
        series = series.sort_index().dropna()
        if len(series) < 5:
            continue
        last_price = series.iloc[-1]
        as_of_date = str(series.index[-1])

        def _ret(days: int) -> Optional[float]:
            if len(series) < days + 1:
                return None
            past = series.iloc[-(days + 1)]
            if past == 0:
                return None
            return round(((last_price / past) - 1) * 100, 2)

        r1w = _ret(5)   # ~1 minggu trading
        r1m = _ret(21)  # ~1 bulan trading
        r3m = _ret(63)  # ~3 bulan trading

        score = _momentum_score(r1w, r1m, r3m)
        results.append(SectorMomentum(
            sector=sector,
            return_1w=r1w,
            return_1m=r1m,
            return_3m=r3m,
            momentum_score=score,
            signal=_signal(score),
        ))

    if not results:
        return RotationReport(
            top_sectors=[], bottom_sectors=[], all_sectors=[],
            rotation_detected=False,
            rotation_note="Data tidak cukup untuk analisis rotasi",
        )

    results.sort(key=lambda s: s.momentum_score, reverse=True)

    top = [s for s in results if s.signal == "ACCUMULATE"]
    bottom = [s for s in results if s.signal == "DISTRIBUTE"]

    # Rotasi terdeteksi jika spread top–bottom > 10%
    rotation_detected = False
    rotation_note = "Pasar bergerak merata — tidak ada rotasi signifikan"
    if top and bottom:
        spread = top[0].momentum_score - bottom[-1].momentum_score
        if spread > 10.0:
            rotation_detected = True
            rotation_note = (
                f"Rotasi terdeteksi: modal bergerak dari {bottom[-1].sector} "
                f"→ {top[0].sector} (spread {spread:.1f}%)"
            )

    return RotationReport(
        top_sectors=top[:3],
        bottom_sectors=bottom[-3:],
        all_sectors=results,
        rotation_detected=rotation_detected,
        rotation_note=rotation_note,
        as_of=as_of_date,
    )
