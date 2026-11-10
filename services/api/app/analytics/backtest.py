"""
R16 — Backtesting Engine.

Simulasi sinyal buy/sell pada data historis OHLCV.
Strategi yang didukung:
  - SMA_CROSSOVER : beli saat SMA50 > SMA200, jual saat SMA50 < SMA200
  - RSI_MEAN_REVERT: beli saat RSI < oversold_threshold, jual saat RSI > overbought_threshold
  - MACD_SIGNAL    : beli saat MACD hist positif, jual saat negatif

Output: equity curve, trade log, metrik (Sharpe, max drawdown, CAGR, win rate).

Batasan desain (V1):
- Hanya long (tidak ada short selling)
- Fully-invested: seluruh modal masuk saat sinyal BUY, keluar saat SELL
- Tidak ada biaya transaksi default (bisa diset via fee_pct)
- Tidak ada slippage modelling
- Tidak ada leverage
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

import math
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Config & Enums
# ---------------------------------------------------------------------------

class BacktestStrategy(str, Enum):
    SMA_CROSSOVER  = "SMA_CROSSOVER"
    RSI_MEAN_REVERT = "RSI_MEAN_REVERT"
    MACD_SIGNAL    = "MACD_SIGNAL"


@dataclass
class BacktestConfig:
    strategy: BacktestStrategy = BacktestStrategy.SMA_CROSSOVER
    initial_capital: float = 10_000_000.0   # IDR default
    fee_pct: float = 0.0015                 # 0.15% per sisi (IDX typical)

    # SMA_CROSSOVER params
    sma_fast: int = 50
    sma_slow: int = 200

    # RSI_MEAN_REVERT params
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    # MACD params
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


# ---------------------------------------------------------------------------
# Output structs
# ---------------------------------------------------------------------------

@dataclass
class TradeRecord:
    entry_date: date
    exit_date: Optional[date]
    entry_price: float
    exit_price: Optional[float]
    shares: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    is_open: bool = True


@dataclass
class EquityPoint:
    date: date
    equity: float
    drawdown_pct: float    # 0 to -1


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    sharpe_ratio: Optional[float]
    max_drawdown_pct: float        # negative number, e.g. -0.25 = -25%
    win_rate_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: Optional[float]
    bars_used: int
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _macd(series: pd.Series, fast: int, slow: int, signal: int):
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return hist


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

def _signals_sma_crossover(df: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    sma_f = _sma(df["close"], cfg.sma_fast)
    sma_s = _sma(df["close"], cfg.sma_slow)
    # 1=BUY entry, -1=SELL/EXIT, 0=HOLD
    signal = pd.Series(0, index=df.index)
    cross_up   = (sma_f > sma_s) & (sma_f.shift(1) <= sma_s.shift(1))
    cross_down = (sma_f < sma_s) & (sma_f.shift(1) >= sma_s.shift(1))
    signal[cross_up]   = 1
    signal[cross_down] = -1
    return signal


def _signals_rsi(df: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    rsi = _rsi(df["close"], cfg.rsi_period)
    signal = pd.Series(0, index=df.index)
    buy  = (rsi < cfg.rsi_oversold)  & (rsi.shift(1) >= cfg.rsi_oversold)
    sell = (rsi > cfg.rsi_overbought) & (rsi.shift(1) <= cfg.rsi_overbought)
    signal[buy]  = 1
    signal[sell] = -1
    return signal


def _signals_macd(df: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    hist = _macd(df["close"], cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    signal = pd.Series(0, index=df.index)
    cross_up   = (hist > 0) & (hist.shift(1) <= 0)
    cross_down = (hist < 0) & (hist.shift(1) >= 0)
    signal[cross_up]   = 1
    signal[cross_down] = -1
    return signal


# ---------------------------------------------------------------------------
# Portfolio simulation
# ---------------------------------------------------------------------------

def _simulate(df: pd.DataFrame, signals: pd.Series, cfg: BacktestConfig) -> tuple[list[TradeRecord], list[EquityPoint]]:
    capital = cfg.initial_capital
    position_shares: float = 0.0
    entry_price: float = 0.0
    entry_date: Optional[date] = None
    trades: list[TradeRecord] = []
    equity_curve: list[EquityPoint] = []
    peak_equity = capital

    for i, (idx, row) in enumerate(df.iterrows()):
        price = float(row["close"])
        sig = signals.iloc[i]
        in_position = position_shares > 0

        # BUY signal — masuk posisi jika belum hold
        if sig == 1 and not in_position:
            cost = capital * (1 - cfg.fee_pct)
            position_shares = cost / price
            entry_price = price
            entry_date = row["session_date"]
            capital = 0.0

        # SELL signal — keluar posisi jika sedang hold
        elif sig == -1 and in_position:
            proceeds = position_shares * price * (1 - cfg.fee_pct)
            pnl = proceeds - (position_shares * entry_price)
            pnl_pct = (price / entry_price - 1) * 100
            trades.append(TradeRecord(
                entry_date=entry_date or row["session_date"],
                exit_date=row["session_date"],
                entry_price=entry_price,
                exit_price=price,
                shares=position_shares,
                pnl=pnl,
                pnl_pct=pnl_pct,
                is_open=False,
            ))
            capital = proceeds
            position_shares = 0.0
            entry_price = 0.0
            entry_date = None

        # Hitung ekuitas hari ini
        equity = capital + (position_shares * price if position_shares > 0 else 0)
        peak_equity = max(peak_equity, equity)
        drawdown = (equity - peak_equity) / peak_equity if peak_equity > 0 else 0.0
        equity_curve.append(EquityPoint(
            date=row["session_date"],
            equity=equity,
            drawdown_pct=drawdown,
        ))

    # Tutup posisi terbuka di akhir periode
    if position_shares > 0 and not df.empty:
        last = df.iloc[-1]
        price = float(last["close"])
        proceeds = position_shares * price * (1 - cfg.fee_pct)
        pnl = proceeds - (position_shares * entry_price)
        pnl_pct = (price / entry_price - 1) * 100
        trades.append(TradeRecord(
            entry_date=entry_date or last["session_date"],
            exit_date=last["session_date"],
            entry_price=entry_price,
            exit_price=price,
            shares=position_shares,
            pnl=pnl,
            pnl_pct=pnl_pct,
            is_open=True,  # posisi masih terbuka saat backtest selesai
        ))

    return trades, equity_curve


# ---------------------------------------------------------------------------
# Metrik kalkulasi
# ---------------------------------------------------------------------------

def _cagr(initial: float, final: float, days: int) -> float:
    if initial <= 0 or days <= 0:
        return 0.0
    years = days / 365.0
    if years < 0.01:
        return 0.0
    return ((final / initial) ** (1 / years) - 1) * 100


def _sharpe(equity_curve: list[EquityPoint], risk_free_annual: float = 0.06) -> Optional[float]:
    if len(equity_curve) < 20:
        return None
    equities = [e.equity for e in equity_curve]
    daily_returns = [(equities[i] / equities[i - 1] - 1) for i in range(1, len(equities))]
    if not daily_returns:
        return None
    arr = np.array(daily_returns)
    mean_r = arr.mean()
    std_r  = arr.std(ddof=1)
    if std_r == 0:
        return None
    rf_daily = risk_free_annual / 252
    return float((mean_r - rf_daily) / std_r * math.sqrt(252))


def _max_drawdown(equity_curve: list[EquityPoint]) -> float:
    if not equity_curve:
        return 0.0
    return min(e.drawdown_pct for e in equity_curve)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_MIN_BARS = 60   # minimal bar untuk backtest bermakna


def run_backtest(
    symbol: str,
    df: pd.DataFrame,
    cfg: Optional[BacktestConfig] = None,
) -> BacktestResult:
    """
    Jalankan backtest pada DataFrame harga historis.

    df harus punya kolom: session_date (date), close (float).
    Kolom lain (open, high, low, volume) diabaikan jika tidak ada.
    """
    if cfg is None:
        cfg = BacktestConfig()

    warnings: list[str] = []

    if df.empty or len(df) < _MIN_BARS:
        warnings.append(f"Data tidak cukup: {len(df)} bar, minimal {_MIN_BARS}")
        return BacktestResult(
            symbol=symbol,
            strategy=cfg.strategy.value,
            start_date=date.today(),
            end_date=date.today(),
            initial_capital=cfg.initial_capital,
            final_equity=cfg.initial_capital,
            total_return_pct=0.0,
            cagr_pct=0.0,
            sharpe_ratio=None,
            max_drawdown_pct=0.0,
            win_rate_pct=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            avg_win_pct=0.0,
            avg_loss_pct=0.0,
            profit_factor=None,
            bars_used=len(df),
            equity_curve=[],
            trades=[],
            warnings=warnings,
        )

    df = df.sort_values("session_date").reset_index(drop=True)
    df["close"] = df["close"].astype(float)

    # Generate signals
    if cfg.strategy == BacktestStrategy.SMA_CROSSOVER:
        signals = _signals_sma_crossover(df, cfg)
        if len(df) < cfg.sma_slow + 10:
            warnings.append(f"Data terlalu pendek untuk SMA{cfg.sma_slow} (punya {len(df)} bar)")
    elif cfg.strategy == BacktestStrategy.RSI_MEAN_REVERT:
        signals = _signals_rsi(df, cfg)
    else:
        signals = _signals_macd(df, cfg)

    trades, equity_curve = _simulate(df, signals, cfg)

    if not equity_curve:
        final_equity = cfg.initial_capital
    else:
        final_equity = equity_curve[-1].equity

    start_date = df.iloc[0]["session_date"]
    end_date   = df.iloc[-1]["session_date"]
    days = (end_date - start_date).days

    total_return = (final_equity / cfg.initial_capital - 1) * 100
    cagr = _cagr(cfg.initial_capital, final_equity, days)
    sharpe = _sharpe(equity_curve)
    max_dd = _max_drawdown(equity_curve)

    closed = [t for t in trades if not t.is_open]
    winners = [t for t in closed if t.pnl > 0]
    losers  = [t for t in closed if t.pnl <= 0]

    win_rate = (len(winners) / len(closed) * 100) if closed else 0.0
    avg_win  = (sum(t.pnl_pct for t in winners) / len(winners)) if winners else 0.0
    avg_loss = (sum(t.pnl_pct for t in losers)  / len(losers))  if losers  else 0.0

    gross_profit = sum(t.pnl for t in winners)
    gross_loss   = abs(sum(t.pnl for t in losers))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    if len(trades) == 0:
        warnings.append("Tidak ada sinyal trade yang dihasilkan selama periode ini")

    return BacktestResult(
        symbol=symbol,
        strategy=cfg.strategy.value,
        start_date=start_date,
        end_date=end_date,
        initial_capital=cfg.initial_capital,
        final_equity=round(final_equity, 2),
        total_return_pct=round(total_return, 2),
        cagr_pct=round(cagr, 2),
        sharpe_ratio=round(sharpe, 3) if sharpe is not None else None,
        max_drawdown_pct=round(max_dd * 100, 2),
        win_rate_pct=round(win_rate, 1),
        total_trades=len(trades),
        winning_trades=len(winners),
        losing_trades=len(losers),
        avg_win_pct=round(avg_win, 2),
        avg_loss_pct=round(avg_loss, 2),
        profit_factor=round(profit_factor, 3) if profit_factor is not None else None,
        bars_used=len(df),
        equity_curve=equity_curve,
        trades=trades,
        warnings=warnings,
    )
