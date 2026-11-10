"""Unit tests untuk R16 Backtesting Engine."""
import pytest
from datetime import date, timedelta

import pandas as pd

from app.analytics.backtest import (
    BacktestConfig,
    BacktestStrategy,
    run_backtest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(prices: list[float], start: date | None = None) -> pd.DataFrame:
    """Buat DataFrame harga sederhana dari list harga."""
    if start is None:
        start = date(2023, 1, 1)
    dates = [start + timedelta(days=i) for i in range(len(prices))]
    return pd.DataFrame({"session_date": dates, "close": prices})


def _trending_up(n: int = 300) -> list[float]:
    """Harga naik linear 100 → 200."""
    return [100 + (i / n) * 100 for i in range(n)]


def _trending_down(n: int = 300) -> list[float]:
    """Harga turun linear 200 → 100."""
    return [200 - (i / n) * 100 for i in range(n)]


def _flat(n: int = 300, price: float = 1000.0) -> list[float]:
    return [price] * n


def _oscillating(n: int = 300) -> list[float]:
    """Harga naik-turun seperti gelombang sinus."""
    import math
    return [1000 + 200 * math.sin(i * 0.2) for i in range(n)]


# ---------------------------------------------------------------------------
# Data tidak cukup
# ---------------------------------------------------------------------------

def test_insufficient_data_returns_warning():
    df = _make_df([1000.0] * 30)  # kurang dari MIN_BARS=60
    result = run_backtest("TEST", df)
    assert result.total_trades == 0
    assert len(result.warnings) > 0
    assert result.final_equity == result.initial_capital


def test_empty_df_returns_warning():
    df = pd.DataFrame(columns=["session_date", "close"])
    result = run_backtest("TEST", df)
    assert result.total_trades == 0
    assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# SMA_CROSSOVER
# ---------------------------------------------------------------------------

def test_sma_crossover_trending_up_profitable():
    df = _make_df(_trending_up(300))
    cfg = BacktestConfig(strategy=BacktestStrategy.SMA_CROSSOVER, sma_fast=20, sma_slow=50)
    result = run_backtest("TEST", df, cfg)
    assert result.strategy == "SMA_CROSSOVER"
    assert result.bars_used == 300
    # Pada tren naik, SMA crossover biasanya profitable
    assert result.final_equity >= result.initial_capital


def test_sma_crossover_trending_down_fewer_trades():
    df = _make_df(_trending_down(300))
    cfg = BacktestConfig(strategy=BacktestStrategy.SMA_CROSSOVER, sma_fast=20, sma_slow=50)
    result = run_backtest("TEST", df, cfg)
    # Tidak ada sinyal BUY pada tren turun (SMA fast tidak pernah > SMA slow)
    assert result.total_trades == 0 or result.total_return_pct <= 0


# ---------------------------------------------------------------------------
# RSI_MEAN_REVERT
# ---------------------------------------------------------------------------

def test_rsi_mean_revert_runs():
    df = _make_df(_oscillating(200))
    cfg = BacktestConfig(
        strategy=BacktestStrategy.RSI_MEAN_REVERT,
        rsi_oversold=35,
        rsi_overbought=65,
    )
    result = run_backtest("TEST", df, cfg)
    assert result.strategy == "RSI_MEAN_REVERT"
    assert result.bars_used == 200


def test_rsi_on_flat_no_trades():
    df = _make_df(_flat(200))
    cfg = BacktestConfig(strategy=BacktestStrategy.RSI_MEAN_REVERT)
    result = run_backtest("TEST", df, cfg)
    # Harga flat → RSI tidak menyentuh oversold/overbought → tidak ada trade
    assert result.total_trades == 0


# ---------------------------------------------------------------------------
# MACD_SIGNAL
# ---------------------------------------------------------------------------

def test_macd_signal_runs():
    df = _make_df(_oscillating(200))
    cfg = BacktestConfig(strategy=BacktestStrategy.MACD_SIGNAL)
    result = run_backtest("TEST", df, cfg)
    assert result.strategy == "MACD_SIGNAL"


# ---------------------------------------------------------------------------
# Metrik
# ---------------------------------------------------------------------------

def test_metrics_bounded():
    df = _make_df(_trending_up(300))
    cfg = BacktestConfig(strategy=BacktestStrategy.SMA_CROSSOVER, sma_fast=20, sma_slow=50)
    result = run_backtest("TEST", df, cfg)
    assert 0.0 <= result.win_rate_pct <= 100.0
    assert result.max_drawdown_pct <= 0.0  # drawdown selalu negatif atau nol
    assert result.bars_used == 300


def test_sharpe_ratio_returned_on_enough_data():
    # Gunakan data osilasi + RSI agar ada variasi equity → std_r > 0 → Sharpe terhitung
    df = _make_df(_oscillating(300))
    cfg = BacktestConfig(
        strategy=BacktestStrategy.RSI_MEAN_REVERT,
        rsi_oversold=35,
        rsi_overbought=65,
    )
    result = run_backtest("TEST", df, cfg)
    # Dengan 300 bar dan equity yang bervariasi, Sharpe harus tersedia
    assert result.sharpe_ratio is not None


def test_equity_curve_length_matches_bars():
    df = _make_df(_oscillating(150))
    cfg = BacktestConfig(strategy=BacktestStrategy.RSI_MEAN_REVERT)
    result = run_backtest("TEST", df, cfg)
    assert len(result.equity_curve) == 150


def test_equity_starts_at_initial_capital():
    df = _make_df(_oscillating(150))
    cfg = BacktestConfig(strategy=BacktestStrategy.RSI_MEAN_REVERT, initial_capital=5_000_000)
    result = run_backtest("TEST", df, cfg)
    if result.equity_curve:
        # Hari pertama (belum ada trade) equity = initial_capital
        assert result.equity_curve[0].equity == pytest.approx(cfg.initial_capital, rel=0.01)


# ---------------------------------------------------------------------------
# Trade records
# ---------------------------------------------------------------------------

def test_all_closed_trades_have_exit():
    df = _make_df(_oscillating(200))
    cfg = BacktestConfig(strategy=BacktestStrategy.RSI_MEAN_REVERT, rsi_oversold=35, rsi_overbought=65)
    result = run_backtest("TEST", df, cfg)
    for trade in result.trades:
        if not trade.is_open:
            assert trade.exit_date is not None
            assert trade.exit_price is not None


def test_winning_plus_losing_equals_closed():
    df = _make_df(_oscillating(200))
    cfg = BacktestConfig(strategy=BacktestStrategy.RSI_MEAN_REVERT, rsi_oversold=35, rsi_overbought=65)
    result = run_backtest("TEST", df, cfg)
    closed = sum(1 for t in result.trades if not t.is_open)
    assert result.winning_trades + result.losing_trades == closed


# ---------------------------------------------------------------------------
# Fee impact
# ---------------------------------------------------------------------------

def test_fee_reduces_return():
    df = _make_df(_trending_up(300))
    cfg_no_fee  = BacktestConfig(strategy=BacktestStrategy.SMA_CROSSOVER, sma_fast=20, sma_slow=50, fee_pct=0.0)
    cfg_with_fee = BacktestConfig(strategy=BacktestStrategy.SMA_CROSSOVER, sma_fast=20, sma_slow=50, fee_pct=0.005)
    r_no  = run_backtest("TEST", df.copy(), cfg_no_fee)
    r_fee = run_backtest("TEST", df.copy(), cfg_with_fee)
    if r_no.total_trades > 0:
        assert r_no.final_equity >= r_fee.final_equity
