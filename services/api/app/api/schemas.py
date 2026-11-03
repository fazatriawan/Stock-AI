"""
Pydantic schemas untuk request/response API.
Semua DTO boundary di sini — TypedDict tidak dipakai di boundary.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

class InstrumentResponse(BaseModel):
    id: str
    canonical_symbol: str
    local_symbol: str
    exchange: str
    country: str
    currency: str
    timezone: str
    asset_type: str
    sector: Optional[str]
    industry: Optional[str]
    company_name: Optional[str]
    status: str

    model_config = {"from_attributes": True}


class InstrumentSearchResponse(BaseModel):
    results: list[InstrumentResponse]
    query: str
    count: int


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------

class PriceBarResponse(BaseModel):
    session_date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: float
    adj_close: Optional[float]
    volume: Optional[int]
    provider: str
    is_adjusted: bool

    model_config = {"from_attributes": True}

    @field_validator("open", "high", "low", "close", "adj_close", mode="before")
    @classmethod
    def decimal_to_float(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        return float(v)


class PriceHistoryResponse(BaseModel):
    instrument: InstrumentResponse
    bars: list[PriceBarResponse]
    count: int
    start: Optional[date]
    end: Optional[date]
    provider: str
    as_of: datetime


# ---------------------------------------------------------------------------
# Staleness / data health
# ---------------------------------------------------------------------------

class StocknessStatus(BaseModel):
    stale: bool
    reason: Optional[str] = None
    last_date: Optional[str] = None
    expected: Optional[str] = None


class ProviderHealthResponse(BaseModel):
    provider: str
    status: str
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    latency_ms: Optional[float] = None
    notes: Optional[str] = None


class DataHealthResponse(BaseModel):
    providers: list[ProviderHealthResponse]
    checked_at: datetime


# ---------------------------------------------------------------------------
# Market status
# ---------------------------------------------------------------------------

class MarketStatusResponse(BaseModel):
    exchange: str
    timezone: str
    is_trading_day: bool
    is_eod_data_ready: bool
    session_date: date
    as_of: datetime


# ---------------------------------------------------------------------------
# Technical snapshot
# ---------------------------------------------------------------------------

class TechnicalSnapshotResponse(BaseModel):
    instrument_id: str
    as_of: date
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_20: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    atr_14: Optional[float] = None
    realized_vol_20: Optional[float] = None
    above_sma_20: Optional[bool] = None
    above_sma_50: Optional[bool] = None
    above_sma_200: Optional[bool] = None
    golden_cross: Optional[bool] = None
    return_1d: Optional[float] = None
    return_5d: Optional[float] = None
    return_20d: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    percentile_52w: Optional[float] = None
    volume_ratio_20: Optional[float] = None
    bars_available: int = 0
    sufficient_data: bool = False
    missing_indicators: list[str] = []


# ---------------------------------------------------------------------------
# Fundamental snapshot
# ---------------------------------------------------------------------------

class FundamentalSnapshotResponse(BaseModel):
    instrument_id: str
    as_of: date
    sector: Optional[str] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    roe: Optional[float] = None
    eps: Optional[float] = None
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    market_cap: Optional[float] = None
    dividend_yield: Optional[float] = None
    debt_to_equity: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    # Bank
    nim: Optional[float] = None
    npl_gross: Optional[float] = None
    car: Optional[float] = None
    metrics_available: list[str] = []
    metrics_missing: list[str] = []
    data_freshness: str = "UNKNOWN"
    period_end: Optional[date] = None


# ---------------------------------------------------------------------------
# Stock overview
# ---------------------------------------------------------------------------

class StockOverviewResponse(BaseModel):
    instrument: InstrumentResponse
    last_price: Optional[float] = None
    last_price_date: Optional[date] = None
    price_provider: Optional[str] = None
    price_stale: bool = False
    technical: Optional[TechnicalSnapshotResponse] = None
    fundamental: Optional[FundamentalSnapshotResponse] = None
    as_of: datetime


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

class FactorScoresResponse(BaseModel):
    fundamental: Optional[float] = None
    valuation: Optional[float] = None
    technical: Optional[float] = None
    macro_policy: Optional[float] = None
    risk_quality: Optional[float] = None
    events_news: Optional[float] = None
    ownership_flows: Optional[float] = None
    composite: float = 0.0
    coverage: float = 0.0


class RecommendationResponse(BaseModel):
    instrument_id: str
    canonical_symbol: str
    as_of: datetime
    action: str
    urgency: str
    horizon: str
    hard_gate_status: str
    hard_gate_reason: Optional[str] = None
    factor_scores: FactorScoresResponse
    evidence_confidence: str
    owned: bool
    bull_thesis: list[str] = []
    bear_case: list[str] = []
    conditions_to_buy: list[str] = []
    conditions_to_sell: list[str] = []
    invalidation_triggers: list[str] = []
    data_gaps: list[str] = []
    changed_from: Optional[str] = None
    human_approval_required: bool = True
    disclaimer: str = (
        "Ini adalah alat analisis dengan keterbatasan dan ketidakpastian, "
        "bukan nasihat investasi. Keputusan transaksi sepenuhnya menjadi tanggung jawab pengguna."
    )


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

class WatchlistItemRequest(BaseModel):
    canonical_symbol: str
    notes: Optional[str] = None


class WatchlistResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    items: list[dict] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Portfolio / trades
# ---------------------------------------------------------------------------

class TradeRequest(BaseModel):
    canonical_symbol: str
    trade_date: date
    side: str  # BUY / SELL
    shares: Decimal
    price: Decimal
    fee: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    currency: str
    fx_to_base: Optional[Decimal] = None
    source_broker: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        if v.upper() not in ("BUY", "SELL"):
            raise ValueError("side harus BUY atau SELL")
        return v.upper()


class TradeResponse(BaseModel):
    id: str
    canonical_symbol: str
    trade_date: date
    side: str
    shares: float
    price: float
    fee: float
    tax: float
    currency: str
    import_fingerprint: Optional[str] = None

    model_config = {"from_attributes": True}
