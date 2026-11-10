"""
R16 — Backtest route.

POST /backtest/{symbol}      → jalankan backtest + simpan ke history
GET  /backtest/strategies    → daftar strategi yang tersedia
GET  /backtest/history       → riwayat backtest runs
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import pandas as pd

from app.analytics.backtest import BacktestConfig, BacktestStrategy, run_backtest
from app.api.schemas import BacktestConfigRequest, BacktestResultResponse, EquityPointResponse, BacktestTradeResponse
from app.db.base import new_uuid
from app.db.models import BacktestRun, Instrument, PriceBar
from app.db.session import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/backtest", tags=["backtest"])

_MAX_LOOKBACK_DAYS = 1825   # 5 tahun


async def _load_price_df(instrument_id: str, db: AsyncSession, lookback_days: int) -> pd.DataFrame:
    end = date.today()
    start = end - timedelta(days=lookback_days)
    result = await db.execute(
        select(PriceBar)
        .where(
            PriceBar.instrument_id == instrument_id,
            PriceBar.session_date.between(start, end),
        )
        .order_by(PriceBar.session_date.asc())
    )
    bars = result.scalars().all()
    if not bars:
        return pd.DataFrame()
    return pd.DataFrame([{
        "session_date": b.session_date,
        "close": float(b.close),
    } for b in bars])


@router.post("/{symbol}", response_model=BacktestResultResponse)
async def run_symbol_backtest(
    symbol: str,
    config: BacktestConfigRequest = BacktestConfigRequest(),
    lookback_days: int = Query(365, ge=60, le=1825, description="Jumlah hari historis (60–1825)"),
    db: AsyncSession = Depends(get_db),
) -> BacktestResultResponse:
    """
    Jalankan backtest strategi teknikal pada data historis.

    Strategi yang tersedia:
    - **SMA_CROSSOVER**: beli saat SMA50 melewati SMA200 ke atas, jual saat sebaliknya
    - **RSI_MEAN_REVERT**: beli saat RSI < 30 (oversold), jual saat RSI > 70 (overbought)
    - **MACD_SIGNAL**: beli saat MACD histogram positif, jual saat negatif

    Semua hasil adalah simulasi historis — bukan prediksi atau rekomendasi investasi.
    """
    # Cari instrumen
    result = await db.execute(
        select(Instrument).where(
            (Instrument.canonical_symbol == symbol.upper()) |
            (Instrument.local_symbol == symbol.upper()),
            Instrument.status == "ACTIVE",
        )
    )
    instr = result.scalar_one_or_none()
    if instr is None:
        raise HTTPException(status_code=404, detail=f"Instrumen '{symbol}' tidak ditemukan")

    df = await _load_price_df(instr.id, db, lookback_days)
    if df.empty:
        raise HTTPException(
            status_code=422,
            detail=f"Tidak ada data harga untuk {symbol} dalam {lookback_days} hari terakhir. "
                   "Jalankan /stocks/{symbol}/prices/refresh terlebih dahulu.",
        )

    # Map config request → BacktestConfig
    bt_cfg = BacktestConfig(
        strategy=BacktestStrategy(config.strategy),
        initial_capital=config.initial_capital,
        fee_pct=config.fee_pct,
        sma_fast=config.sma_fast,
        sma_slow=config.sma_slow,
        rsi_period=config.rsi_period,
        rsi_oversold=config.rsi_oversold,
        rsi_overbought=config.rsi_overbought,
        macd_fast=config.macd_fast,
        macd_slow=config.macd_slow,
        macd_signal=config.macd_signal_period,
    )

    bt = run_backtest(symbol=symbol.upper(), df=df, cfg=bt_cfg)

    # Simpan ke backtest_runs (history)
    cfg_hash = hashlib.sha256(
        json.dumps(config.model_dump(), sort_keys=True).encode()
    ).hexdigest()[:16]
    run = BacktestRun(
        id=new_uuid(),
        config_hash=cfg_hash,
        status="DONE",
        symbol=symbol.upper(),
        strategy=config.strategy,
        bars_used=bt.bars_used,
        total_return_pct=bt.total_return_pct,
        cagr_pct=bt.cagr_pct,
        sharpe_ratio=bt.sharpe_ratio,
        max_drawdown_pct=bt.max_drawdown_pct,
        win_rate_pct=bt.win_rate_pct,
        total_trades=bt.total_trades,
        results_json={
            "warnings": bt.warnings,
            "initial_capital": bt.initial_capital,
            "final_equity": bt.final_equity,
        },
    )
    db.add(run)
    await db.commit()

    log.info(
        "backtest.done",
        symbol=symbol,
        strategy=config.strategy,
        total_return_pct=bt.total_return_pct,
        trades=bt.total_trades,
        run_id=run.id,
    )

    return BacktestResultResponse(
        symbol=bt.symbol,
        strategy=bt.strategy,
        start_date=bt.start_date,
        end_date=bt.end_date,
        initial_capital=bt.initial_capital,
        final_equity=bt.final_equity,
        total_return_pct=bt.total_return_pct,
        cagr_pct=bt.cagr_pct,
        sharpe_ratio=bt.sharpe_ratio,
        max_drawdown_pct=bt.max_drawdown_pct,
        win_rate_pct=bt.win_rate_pct,
        total_trades=bt.total_trades,
        winning_trades=bt.winning_trades,
        losing_trades=bt.losing_trades,
        avg_win_pct=bt.avg_win_pct,
        avg_loss_pct=bt.avg_loss_pct,
        profit_factor=bt.profit_factor,
        bars_used=bt.bars_used,
        equity_curve=[
            EquityPointResponse(date=e.date, equity=e.equity, drawdown_pct=e.drawdown_pct)
            for e in bt.equity_curve
        ],
        trades=[
            BacktestTradeResponse(
                entry_date=t.entry_date,
                exit_date=t.exit_date,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                shares=t.shares,
                pnl=t.pnl,
                pnl_pct=t.pnl_pct,
                is_open=t.is_open,
            )
            for t in bt.trades
        ],
        warnings=bt.warnings,
    )


@router.get("/history", response_model=list[dict])
async def get_backtest_history(
    limit: int = Query(20, ge=1, le=100),
    symbol: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Riwayat backtest runs — dapat difilter per symbol."""
    q = select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(limit)
    if symbol:
        q = q.where(BacktestRun.symbol == symbol.upper())
    result = await db.execute(q)
    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "strategy": r.strategy,
            "bars_used": r.bars_used,
            "total_return_pct": float(r.total_return_pct) if r.total_return_pct else None,
            "cagr_pct": float(r.cagr_pct) if r.cagr_pct else None,
            "sharpe_ratio": float(r.sharpe_ratio) if r.sharpe_ratio else None,
            "max_drawdown_pct": float(r.max_drawdown_pct) if r.max_drawdown_pct else None,
            "win_rate_pct": float(r.win_rate_pct) if r.win_rate_pct else None,
            "total_trades": r.total_trades,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in result.scalars().all()
    ]


@router.get("/strategies", response_model=dict)
async def list_strategies() -> dict:
    """Daftar strategi backtest yang tersedia beserta parameter defaultnya."""
    return {
        "strategies": [
            {
                "name": "SMA_CROSSOVER",
                "description": "Golden/Death Cross — beli saat SMA50 > SMA200, jual saat SMA50 < SMA200",
                "params": {"sma_fast": 50, "sma_slow": 200},
                "min_bars_required": 210,
            },
            {
                "name": "RSI_MEAN_REVERT",
                "description": "RSI Mean Reversion — beli saat RSI < 30, jual saat RSI > 70",
                "params": {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70},
                "min_bars_required": 60,
            },
            {
                "name": "MACD_SIGNAL",
                "description": "MACD Histogram crossover — beli saat hist positif, jual saat negatif",
                "params": {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9},
                "min_bars_required": 60,
            },
        ]
    }
