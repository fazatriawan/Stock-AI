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
    # AI enrichment (opsional — hanya tersedia jika ANTHROPIC_API_KEY diset)
    ai_enriched: bool = False
    ai_macro_context: Optional[str] = None
    ai_identified_risks: list[str] = []
    ai_model: Optional[str] = None
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


class TradeResponse(BaseModel):
    """Trade lengkap dengan info instrumen."""
    id: str
    portfolio_id: str
    instrument_id: str
    canonical_symbol: str
    company_name: Optional[str] = None
    trade_date: date
    side: str
    shares: float
    lots: float
    price: float
    fee: float
    tax: float
    currency: str
    source_broker: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Portfolio v1.1 — schemas lengkap
# ---------------------------------------------------------------------------

class TradeCreateRequest(BaseModel):
    """Request untuk menambah trade manual."""
    canonical_symbol: str
    trade_date: date
    side: str  # BUY / SELL
    shares: float
    price: float
    fee: float = 0.0
    tax: float = 0.0
    currency: Optional[str] = None
    source_broker: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        if v.upper() not in ("BUY", "SELL"):
            raise ValueError("side harus BUY atau SELL")
        return v.upper()

    @field_validator("shares", "price")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Nilai harus positif")
        return v


class PositionResponse(BaseModel):
    """Posisi aktif per instrumen dengan P/L tidak terealisasi."""
    instrument_id: str
    canonical_symbol: str
    company_name: Optional[str] = None
    exchange: str
    currency: str
    sector: Optional[str] = None

    shares: float
    lots: float
    avg_cost: float
    total_cost: float

    current_price: Optional[float] = None
    current_price_date: Optional[date] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None

    weight: float = 0.0
    trade_count: int = 0
    first_buy_date: Optional[date] = None
    last_trade_date: Optional[date] = None


class PortfolioSummaryResponse(BaseModel):
    """Ringkasan portofolio lengkap."""
    portfolio_id: str
    portfolio_name: str
    base_currency: str
    as_of: datetime

    total_invested: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    positions: list[PositionResponse]
    sector_weights: dict[str, float]
    concentration_warnings: list[str]
    trade_count: int


class PortfolioSeedResponse(BaseModel):
    """Hasil seed portofolio awal."""
    message: str
    portfolio_id: str
    created: int
    skipped: int
    errors: list[str]


# ---------------------------------------------------------------------------
# Import pipeline (Phase 2)
# ---------------------------------------------------------------------------

class ParsedTradePreview(BaseModel):
    """Satu baris transaksi yang diparsing — belum di-commit ke DB."""
    row_number: int
    canonical_symbol: str
    trade_date: date
    side: str
    lots: float
    shares: float
    price: float
    fee: float
    tax: float
    currency: str
    source_broker: str
    fingerprint: str
    status: str          # OK / WARNING / ERROR
    warnings: list[str]
    errors: list[str]


class ImportPreviewResponse(BaseModel):
    """Hasil parsing file sebelum commit — tampilkan ke user untuk verifikasi."""
    broker_format: str
    total_rows: int
    valid_count: int
    error_count: int
    duplicate_count: int   # sudah ada di DB
    trades: list[ParsedTradePreview]
    parse_errors: list[str]
    warnings: list[str]


class ImportConfirmRequest(BaseModel):
    """Request untuk commit trades yang sudah divalidasi user."""
    trades: list[ParsedTradePreview]
    skip_duplicates: bool = True   # abaikan yang sudah ada (default)


class ImportConfirmResponse(BaseModel):
    """Hasil commit import."""
    message: str
    created: int
    skipped_duplicates: int
    skipped_errors: int
    errors: list[str]


# ---------------------------------------------------------------------------
# Portfolio Intelligence (Phase 3)
# ---------------------------------------------------------------------------

class ConcentrationRiskResponse(BaseModel):
    symbol: str
    weight: float
    severity: str
    message: str


class SectorRiskResponse(BaseModel):
    sector: str
    weight: float
    severity: str
    message: str


class PortfolioHealthResponse(BaseModel):
    """Laporan kesehatan portofolio — skor, konsentrasi, diversifikasi."""
    health_score: float
    grade: str   # EXCELLENT / GOOD / FAIR / POOR
    position_count: int
    diversification_score: float
    concentration_risks: list[ConcentrationRiskResponse]
    sector_risks: list[SectorRiskResponse]
    largest_position_symbol: Optional[str] = None
    largest_position_weight: float
    total_invested: float
    total_market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    diversification_component: float
    concentration_component: float
    pnl_component: float
    warnings: list[str]
    recommendations: list[str]


class LossScenarioResponse(BaseModel):
    scenario: str
    label: str
    description: str
    projected_loss_idr: float
    projected_loss_pct: float
    remaining_exposure_idr: float
    breakeven_price: Optional[float] = None
    pros: list[str]
    cons: list[str]
    risk_level: str


class LossPositionResponse(BaseModel):
    """Analisis posisi rugi dengan 5 skenario aksi."""
    canonical_symbol: str
    company_name: Optional[str] = None
    shares: float
    lots: float
    avg_cost: float
    current_price: float
    total_cost: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    scenarios: list[LossScenarioResponse]
    suggested_scenario: str
    suggested_reason: str


class LossAnalyzerResponse(BaseModel):
    """Semua posisi rugi dengan analisis skenario."""
    loss_positions: list[LossPositionResponse]
    total_loss_positions: int
    total_unrealized_loss_idr: float
    as_of: datetime


# ---------------------------------------------------------------------------
# Rebalance simulator (Phase 4)
# ---------------------------------------------------------------------------

class TargetAllocationResponse(BaseModel):
    canonical_symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    current_lots: float
    current_weight: float
    target_weight: float
    current_market_value: float
    target_market_value: float
    delta_value: float
    delta_lots: float
    action: str     # BUY / SELL / HOLD
    note: str


class RebalanceSimulationResponse(BaseModel):
    """Hasil simulasi rebalancing ke target bobot."""
    total_portfolio_value: float
    positions_count: int
    allocations: list[TargetAllocationResponse]
    buy_actions: int
    sell_actions: int
    hold_actions: int
    total_buy_value: float
    total_sell_value: float
    net_cash_needed: float
    disclaimer: str


class RebalanceRequest(BaseModel):
    """Request simulasi rebalancing — target_weights opsional (default: equal weight)."""
    target_weights: dict[str, float] = {}   # {canonical_symbol: weight (0–1)}
    new_capital: float = 0.0


class AllocationSuggestionResponse(BaseModel):
    canonical_symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    current_weight: float
    suggested_new_amount: float
    suggested_lots: float
    rationale: str
    priority: int


class CapitalAllocationResponse(BaseModel):
    """Rencana alokasi modal baru."""
    new_capital: float
    total_positions: int
    suggestions: list[AllocationSuggestionResponse]
    undiversified_warning: Optional[str] = None
    disclaimer: str


class CapitalAllocationRequest(BaseModel):
    new_capital: float


# ---------------------------------------------------------------------------
# Decision Journal (Phase 5)
# ---------------------------------------------------------------------------

class JournalEntryCreateRequest(BaseModel):
    canonical_symbol: str
    decision_date: date
    action: str                      # BUY / SELL / HOLD / WATCH
    rationale: str
    thesis: Optional[str] = None
    invalidation: Optional[str] = None
    price_at_decision: Optional[float] = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {"BUY", "SELL", "HOLD", "WATCH"}
        if v.upper() not in allowed:
            raise ValueError(f"action harus salah satu dari: {allowed}")
        return v.upper()


class JournalReviewRequest(BaseModel):
    outcome: str    # CORRECT / INCORRECT / PENDING
    outcome_notes: Optional[str] = None

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v: str) -> str:
        allowed = {"CORRECT", "INCORRECT", "PENDING"}
        if v.upper() not in allowed:
            raise ValueError(f"outcome harus salah satu dari: {allowed}")
        return v.upper()


class JournalEntryResponse(BaseModel):
    id: str
    canonical_symbol: str
    decision_date: date
    action: str
    rationale: str
    thesis: Optional[str] = None
    invalidation: Optional[str] = None
    price_at_decision: Optional[float] = None
    outcome: Optional[str] = None
    outcome_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Daily Intelligence (Phase 5)
# ---------------------------------------------------------------------------

class DailyPositionBrief(BaseModel):
    canonical_symbol: str
    company_name: Optional[str] = None
    lots: float
    avg_cost: float
    current_price: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    weight: float
    action: Optional[str] = None        # dari recommendation engine jika ada
    urgency: Optional[str] = None
    data_stale: bool = False


class DailyIntelligenceResponse(BaseModel):
    as_of: datetime
    market_open: bool
    total_positions: int
    total_market_value: float
    unrealized_pnl_pct: float
    positions: list[DailyPositionBrief]
    alerts: list[str]      # konsentrasi, posisi rugi besar, dll
    data_freshness: str    # "FRESH" / "STALE" / "PARTIAL"


# ---------------------------------------------------------------------------
# Phase D — Decisions
# ---------------------------------------------------------------------------

class DecisionSummaryResponse(BaseModel):
    instrument_id: str
    canonical_symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    action: str                     # BUY / WAIT / ADD_CANDIDATE / HOLD / TRIM_CANDIDATE / SELL / INSUFFICIENT_DATA
    urgency: str                    # NORMAL / REVIEW_NOW
    composite_score: float          # 0–100
    evidence_confidence: str        # LOW / MEDIUM / HIGH
    hard_gate_status: str
    hard_gate_reason: Optional[str] = None
    owned: bool
    portfolio_weight: Optional[float] = None   # % jika dimiliki
    current_price: Optional[float] = None
    bull_thesis: list[str] = []
    bear_case: list[str] = []
    data_gaps: list[str] = []
    factor_scores: dict[str, Optional[float]] = {}


class DecisionListResponse(BaseModel):
    decisions: list[DecisionSummaryResponse]
    total: int
    action_counts: dict[str, int]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Phase D — Screener
# ---------------------------------------------------------------------------

class ScreenerResultResponse(BaseModel):
    instrument_id: str
    canonical_symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    exchange: Optional[str] = None
    current_price: Optional[float] = None
    action: str
    composite_score: float
    evidence_confidence: str
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    roe: Optional[float] = None
    dividend_yield: Optional[float] = None
    rsi_14: Optional[float] = None
    above_sma_200: Optional[bool] = None
    return_20d: Optional[float] = None
    data_freshness: str = "UNKNOWN"


class ScreenerListResponse(BaseModel):
    results: list[ScreenerResultResponse]
    total: int
    filters_applied: dict[str, Any]
    as_of: datetime


# ---------------------------------------------------------------------------
# Phase D — Performance
# ---------------------------------------------------------------------------

class EquityDataPoint(BaseModel):
    date: date
    portfolio_value: float
    invested: float
    pnl_pct: float      # %


class PositionContribution(BaseModel):
    canonical_symbol: str
    company_name: Optional[str] = None
    total_cost: float
    current_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float   # %
    portfolio_weight: float      # %


class PerformanceResponse(BaseModel):
    equity_curve: list[EquityDataPoint]
    total_return_pct: float
    total_invested: float
    current_value: float
    unrealized_pnl: float
    position_contributions: list[PositionContribution] = []
    best_position: Optional[PositionContribution] = None
    worst_position: Optional[PositionContribution] = None
    as_of: datetime


# ---------------------------------------------------------------------------
# Macro & Policy Events
# ---------------------------------------------------------------------------

class MacroObservationResponse(BaseModel):
    series_id: str
    label: str
    value: Optional[float] = None
    observed_date: date
    released_at: Optional[datetime] = None


class MacroSnapshotResponse(BaseModel):
    observations: list[MacroObservationResponse]
    total_series: int
    as_of: datetime


class PolicyEventResponse(BaseModel):
    id: str
    event_type: str
    title: str
    summary: Optional[str] = None
    country: Optional[str] = None
    affected_sectors: list[str] = []
    effective_date: Optional[date] = None
    published_at: Optional[datetime] = None
    policy_stage: Optional[str] = None
    materiality: Optional[str] = None
    company_impacts: list[dict] = []


class PolicyEventListResponse(BaseModel):
    events: list[PolicyEventResponse]
    total: int
    as_of: datetime


class PolicyEventCreateRequest(BaseModel):
    event_type: str
    title: str
    summary: Optional[str] = None
    country: Optional[str] = None
    affected_sectors: list[str] = []
    effective_date: Optional[date] = None
    published_at: Optional[datetime] = None
    policy_stage: Optional[str] = None
    materiality: Optional[str] = None


# ---------------------------------------------------------------------------
# Research Notebook
# ---------------------------------------------------------------------------

class NoteCreateRequest(BaseModel):
    title: str
    body: Optional[str] = None
    canonical_symbol: Optional[str] = None
    tags: Optional[list[str]] = None


class NoteUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    canonical_symbol: Optional[str] = None
    tags: Optional[list[str]] = None


class NoteResponse(BaseModel):
    id: str
    title: str
    body: str
    canonical_symbol: Optional[str] = None
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
