"""
Portfolio calculator — hitung posisi dari riwayat trade.
Metode: Weighted Average Cost (WAC).
Aturan: menghitung HARGA RATA-RATA yang benar — jangan diubah tanpa alasan akuntansi jelas.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional


LOT_SIZE_IDX = 100  # 1 lot = 100 saham di IDX


@dataclass
class PositionData:
    """Posisi aktif per instrumen, dihitung dari trade history."""
    instrument_id: str
    canonical_symbol: str = ""
    company_name: Optional[str] = None
    exchange: str = ""
    currency: str = "IDR"
    sector: Optional[str] = None

    # Kuantitas
    shares: float = 0.0           # total saham yang dimiliki saat ini
    lots: float = 0.0             # shares / lot_size (untuk IDX)
    lot_size: int = LOT_SIZE_IDX  # saham per lot

    # Biaya
    avg_cost: float = 0.0         # harga rata-rata beli (termasuk fee)
    total_cost: float = 0.0       # avg_cost * shares

    # Harga pasar (diisi dari luar calculator)
    current_price: Optional[float] = None
    current_price_date: Optional[date] = None

    # P/L
    market_value: Optional[float] = None  # current_price * shares
    unrealized_pnl: Optional[float] = None   # market_value - total_cost
    unrealized_pnl_pct: Optional[float] = None

    # Alokasi portfolio (diisi dari luar)
    weight: float = 0.0  # % dari total portfolio value

    # Trade history summary
    trade_count: int = 0
    first_buy_date: Optional[date] = None
    last_trade_date: Optional[date] = None


@dataclass
class _RawAccumulator:
    """State sementara untuk kalkulasi WAC."""
    shares: float = 0.0
    total_cost: float = 0.0  # termasuk fee
    trade_count: int = 0
    first_buy_date: Optional[date] = None
    last_trade_date: Optional[date] = None


def compute_positions(
    trades: Sequence[Any],  # Sequence[Trade] dari SQLAlchemy
    as_of: Optional[date] = None,
) -> dict[str, PositionData]:
    """
    Hitung posisi aktif dari riwayat trade menggunakan metode WAC.

    Mengembalikan dict {instrument_id: PositionData} untuk posisi dengan shares > 0.
    trade yang melewati `as_of` diabaikan (point-in-time calculation).
    """
    accumulators: dict[str, _RawAccumulator] = {}

    # Sort by date lalu by id untuk determinisme
    sorted_trades = sorted(
        trades,
        key=lambda t: (t.trade_date, t.id),
    )

    for trade in sorted_trades:
        # Filter point-in-time
        if as_of is not None and trade.trade_date > as_of:
            continue

        iid = trade.instrument_id
        if iid not in accumulators:
            accumulators[iid] = _RawAccumulator()

        acc = accumulators[iid]
        acc.trade_count += 1
        acc.last_trade_date = trade.trade_date

        shares = float(trade.shares)
        price = float(trade.price)
        fee = float(trade.fee) if trade.fee is not None else 0.0
        tax = float(trade.tax) if trade.tax is not None else 0.0

        if trade.side == "BUY":
            trade_cost = shares * price + fee + tax
            acc.total_cost += trade_cost
            acc.shares += shares
            if acc.first_buy_date is None:
                acc.first_buy_date = trade.trade_date

        elif trade.side == "SELL":
            # Kurangi porsi biaya proposional (WAC: rata-rata tetap, hanya shares turun)
            if acc.shares > 0:
                avg = acc.total_cost / acc.shares
                sell_cost = avg * shares
                acc.total_cost -= sell_cost
                acc.shares -= shares
                # Prevent floating point drift to negative
                if acc.shares < 1e-6:
                    acc.shares = 0.0
                    acc.total_cost = 0.0

    positions: dict[str, PositionData] = {}
    for iid, acc in accumulators.items():
        if acc.shares < 1e-6:
            continue  # posisi sudah ditutup

        avg_cost = acc.total_cost / acc.shares if acc.shares > 0 else 0.0
        pos = PositionData(
            instrument_id=iid,
            shares=round(acc.shares, 4),
            avg_cost=round(avg_cost, 6),
            total_cost=round(acc.total_cost, 6),
            lots=round(acc.shares / LOT_SIZE_IDX, 2),
            trade_count=acc.trade_count,
            first_buy_date=acc.first_buy_date,
            last_trade_date=acc.last_trade_date,
        )
        positions[iid] = pos

    return positions


def enrich_positions_with_prices(
    positions: dict[str, PositionData],
    prices: dict[str, tuple[float, Any]],  # {instrument_id: (price, date)}
) -> dict[str, PositionData]:
    """Tambahkan harga pasar dan hitung P/L untuk setiap posisi."""
    total_market_value = sum(
        p.shares * price
        for iid, (price, _) in prices.items()
        if iid in positions
        for p in [positions[iid]]
    )

    for iid, pos in positions.items():
        if iid in prices:
            price, price_date = prices[iid]
            pos.current_price = price
            pos.current_price_date = price_date
            pos.market_value = round(pos.shares * price, 2)
            pos.unrealized_pnl = round(pos.market_value - pos.total_cost, 2)
            pos.unrealized_pnl_pct = (
                round(pos.unrealized_pnl / pos.total_cost, 4)
                if pos.total_cost > 0 else None
            )
            if total_market_value > 0:
                pos.weight = round(pos.market_value / total_market_value, 4)

    return positions
