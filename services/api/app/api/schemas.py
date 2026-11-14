"""
Pydantic schemas untuk request/response API.
Semua DTO boundary di sini — TypedDict tidak dipakai di boundary.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


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
    freshness_status: str = "FRESH"

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


class ProviderCapabilityResponse(BaseModel):
    license_status: str
    access_status: str
    cost: str
    granularity: str
    freshness_policy: str
    supports_point_in_time: bool
    datasets: list[str]
    quota_per_day: Optional[int] = None
    quota_remaining: Optional[int] = None
    notes: Optional[str] = None


class DataProviderResponse(BaseModel):
    """Gabungan capability + health untuk satu provider."""
    provider: str
    health_status: str
    license_status: str
    access_status: str
    cost: str
    datasets: list[str]
    granularity: str
    freshness_policy: str
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    notes: Optional[str] = None


class DataProvidersResponse(BaseModel):
    providers: list[DataProviderResponse]
    checked_at: datetime


class CSVImportResponse(BaseModel):
    inserted: int
    skipped_duplicate: int
    skipped_existing_source: bool
    parse_errors: list[str]
    source_id: Optional[str] = None


class FreshnessBreakdown(BaseModel):
    status: str
    count: int


class InstrumentFreshnessResponse(BaseModel):
    instrument_id: str
    total_bars: int
    fresh_bars: int
    stale_bars: int
    other_bars: int
    data_quality_pct: float
    last_fresh_date: Optional[date] = None
    last_bar_date: Optional[date] = None
    breakdown: list[FreshnessBreakdown]


class MarkStaleResponse(BaseModel):
    marked_stale: int
    cutoff_date: date
    instrument_id: Optional[str] = None
    ran_at: datetime


class RefreshStaleResponse(BaseModel):
    instruments_found: int
    instruments_refreshed: int
    bars_added: int
    errors: list[str]
    ran_at: datetime


class CoverageStatusResponse(BaseModel):
    """Distribusi freshness_status seluruh price_bars di DB."""
    fresh: int
    stale: int
    unavailable: int
    quota_exhausted: int
    other: int
    total: int
    stale_pct: float
    unavailable_instruments: int
    quota_instruments: int


class ResetQuotaResponse(BaseModel):
    """Hasil reset QUOTA_EXHAUSTED → STALE."""
    bars_reset: int
    ran_at: datetime


class ProviderQuotaRow(BaseModel):
    """Statistik quota satu provider hari ini."""
    provider_name: str
    calls_today: int
    quota_per_day: Optional[int]
    quota_exhausted: bool
    date_str: str


class ProviderQuotaResponse(BaseModel):
    """Daftar per-provider daily call stats dari quota tracker."""
    providers: list[ProviderQuotaRow]
    total_calls_today: int
    as_of: datetime


class GapReportRow(BaseModel):
    """Gap report untuk satu instrumen."""
    instrument_id: str
    canonical_symbol: str
    exchange: str
    bar_count: int
    expected_bars: int
    gap_pct: float
    first_date: date
    last_date: date
    history_days: int
    severity: str   # "CRITICAL" / "WARNING" / "OK"


class DataGapsResponse(BaseModel):
    """Hasil deteksi gap data OHLCV."""
    reports: list[GapReportRow]
    instruments_checked: int
    with_gaps: int
    ran_at: datetime


class HealGapsResponse(BaseModel):
    """Hasil gap auto-heal — re-ingest instrumen dengan data tidak lengkap."""
    instruments_found: int
    instruments_healed: int
    bars_added: int
    errors: list[str]
    ran_at: datetime


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
# Financial Integrity Checker
# ---------------------------------------------------------------------------

class MetricConflictResponse(BaseModel):
    metric: str
    flag: str
    value: Optional[float] = None
    description: str
    affected_downstream: list[str] = []


class IntegrityReportResponse(BaseModel):
    instrument_id: str
    canonical_symbol: str
    checked_at: datetime
    facts_checked: int
    conflicts: list[MetricConflictResponse]
    blocked_metrics: list[str]
    overall_status: str  # CLEAN | WARNINGS | BLOCKED


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
    integrity_status: str = "UNCHECKED"
    integrity_blocked: list[str] = []


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
# Daily Intelligence (Phase 5 + R12)
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
    # R12 additions
    return_1d: Optional[float] = None
    prev_price: Optional[float] = None


class MarketSessionResponse(BaseModel):
    exchange: str
    is_trading_day: bool
    is_open_now: bool
    local_time_str: str
    next_trading_day: Optional[date] = None


class DigestAlertResponse(BaseModel):
    category: str
    symbol: str
    message: str
    severity: str                       # INFO / WARNING / CRITICAL


class DailyIntelligenceResponse(BaseModel):
    as_of: datetime
    market_open: bool                   # any exchange open (backward compat)
    market_sessions: list[MarketSessionResponse] = []  # R12: per-exchange
    total_positions: int
    total_market_value: float
    unrealized_pnl_pct: float
    positions: list[DailyPositionBrief]
    alerts: list[str]                   # backward compat — string alerts
    structured_alerts: list[DigestAlertResponse] = []  # R12: dengan severity + category
    data_freshness: str    # "FRESH" / "STALE" / "PARTIAL"
    # R12 digest stats
    gainers_count: int = 0
    losers_count: int = 0
    unchanged_count: int = 0


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
# Peer Comparison — R8
# ---------------------------------------------------------------------------

class PeerFundamentalSnapshot(BaseModel):
    """Ringkasan fundamental satu emiten untuk tabel peer comparison."""
    canonical_symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    roe: Optional[float] = None
    eps: Optional[float] = None
    gross_margin: Optional[float] = None
    net_margin: Optional[float] = None
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    market_cap: Optional[float] = None
    dividend_yield: Optional[float] = None
    debt_to_equity: Optional[float] = None
    # Bank-specific
    nim: Optional[float] = None
    npl_gross: Optional[float] = None
    car: Optional[float] = None
    data_freshness: str = "UNKNOWN"
    period_end: Optional[date] = None
    is_subject: bool = False  # True = emiten yang diqueri


class PeerComparisonResponse(BaseModel):
    """Perbandingan fundamental lintas peer di sektor yang sama."""
    subject_symbol: str
    sector: Optional[str]
    peers: list[PeerFundamentalSnapshot]
    peer_count: int
    median_pe: Optional[float] = None
    median_pb: Optional[float] = None
    median_roe: Optional[float] = None
    source: str  # "db" | "sectors_api"
    as_of: datetime


# ---------------------------------------------------------------------------
# Investment Policy Statement (IPS) — BL-05
# ---------------------------------------------------------------------------

class InvestmentPolicyResponse(BaseModel):
    """Snapshot IPS yang sedang aktif."""
    profile_name: str
    mode: str
    max_position_weight: float
    max_sector_weight: float
    buy_score_threshold: float
    min_core_coverage: float
    max_staleness_days: int
    horizon: str
    notes: Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class InvestmentPolicyUpdateRequest(BaseModel):
    """Semua field opsional — hanya kirim yang ingin diubah."""
    mode: Optional[str] = None
    max_position_weight: Optional[float] = None
    max_sector_weight: Optional[float] = None
    buy_score_threshold: Optional[float] = None
    min_core_coverage: Optional[float] = None
    max_staleness_days: Optional[int] = None
    horizon: Optional[str] = None
    notes: Optional[str] = None


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


# ---------------------------------------------------------------------------
# R10: Trade Feasibility
# ---------------------------------------------------------------------------

class FeasibilityCheckResponse(BaseModel):
    name: str
    passed: bool
    is_hard_block: bool
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


class TradeFeasibilityResponse(BaseModel):
    status: str                          # FEASIBLE / MARGINAL / NOT_FEASIBLE
    checks: list[FeasibilityCheckResponse]
    lot_size: int
    min_lots: int
    min_cost_estimate: float
    suggested_lots: Optional[int] = None
    suggested_cost: Optional[float] = None
    adv_ratio: Optional[float] = None
    spread_cost_pct: Optional[float] = None
    warnings: list[str] = []
    blockers: list[str] = []


class TradeFeasibilityRequest(BaseModel):
    available_cash: float
    portfolio_total_value: float
    portfolio_weight_current: float = 0.0
    desired_lots: Optional[int] = None


# ---------------------------------------------------------------------------
# R11: Dividend Sustainability
# ---------------------------------------------------------------------------

class DividendPointResponse(BaseModel):
    year: int
    dps: float
    eps: Optional[float] = None
    fcf_per_share: Optional[float] = None
    payout_ratio: Optional[float] = None
    fcf_payout_ratio: Optional[float] = None


class DividendSustainabilityResponse(BaseModel):
    instrument_id: str
    as_of: date
    rating: str              # STRONG / ADEQUATE / WEAK / UNSUSTAINABLE / INSUFFICIENT_DATA
    trend: str               # GROWING / STABLE / DECLINING / CUT / INITIATED / NO_DATA
    latest_dps: Optional[float] = None
    latest_yield: Optional[float] = None
    payout_ratio: Optional[float] = None
    fcf_payout_ratio: Optional[float] = None
    dgr_3y: Optional[float] = None
    inflation_rate: Optional[float] = None
    real_yield: Optional[float] = None
    history: list[DividendPointResponse] = []
    notes: list[str] = []
    data_gaps: list[str] = []


# ---------------------------------------------------------------------------
# R14: Insider Transactions
# ---------------------------------------------------------------------------

class InsiderTransactionRequest(BaseModel):
    insider_name: str
    insider_role: str                   # DIRECTOR / COMMISSIONER / MAJOR_SHAREHOLDER / OTHER
    transaction_type: str               # BUY / SELL / GRANT / EXERCISE
    transaction_date: date
    shares: int
    price_per_share: Optional[float] = None
    total_value: Optional[float] = None
    currency: str = "IDR"
    shares_owned_after: Optional[int] = None
    ownership_pct_after: Optional[float] = None
    disclosure_date: Optional[date] = None
    source_url: Optional[str] = None
    notes: Optional[str] = None


class InsiderTransactionResponse(BaseModel):
    id: Optional[str] = None
    insider_name: str
    insider_role: str
    transaction_type: str
    transaction_date: date
    shares: int
    price_per_share: Optional[float] = None
    total_value: Optional[float] = None
    currency: str
    shares_owned_after: Optional[int] = None
    ownership_pct_after: Optional[float] = None
    disclosure_date: Optional[date] = None
    source_url: Optional[str] = None


class InsiderImportResponse(BaseModel):
    symbol: str
    inserted: int
    skipped: int


class InsiderSignalResponse(BaseModel):
    symbol: str
    as_of: date
    sentiment: str           # STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL / NO_DATA
    score: float             # -1.0 → +1.0
    net_buy_shares: int
    net_sell_shares: int
    unique_buyers: int
    unique_sellers: int
    cluster_detected: bool
    cluster_type: Optional[str] = None
    lookback_days: int
    transactions_analyzed: int
    latest_date: Optional[date] = None
    summary_text: str
    transactions: list[InsiderTransactionResponse] = []


# ---------------------------------------------------------------------------
# R15: Multibagger Screener
# ---------------------------------------------------------------------------

class ScoreComponentResponse(BaseModel):
    name: str
    score: float
    max_score: float
    notes: str


class ReverseScenarioResponse(BaseModel):
    target_multiple: int
    horizon_years: int
    required_eps_cagr_constant_pe_pct: float
    required_eps_cagr_rerating_pct: Optional[float] = None
    assumed_annual_dilution_pct: float = 2.0
    downside_risk_note: str


class MultibaggerScoreResponse(BaseModel):
    instrument_id: str
    symbol: str
    tier: str                          # STRONG / MODERATE / WEAK / NOT_QUALIFIED / INSUFFICIENT
    total_score: float                 # 0–100
    components: list[ScoreComponentResponse]
    strengths: list[str]
    concerns: list[str]
    data_completeness: float           # 0–1
    pipelines_matched: list[str] = Field(default_factory=list)
    reverse_scenarios: list[ReverseScenarioResponse] = Field(default_factory=list)


class MultibaggerResultResponse(BaseModel):
    instrument_id: str
    canonical_symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    exchange: Optional[str] = None
    current_price: Optional[float] = None
    score: MultibaggerScoreResponse
    pe_ratio: Optional[float] = None
    roe: Optional[float] = None
    net_margin: Optional[float] = None
    revenue_growth_1y: Optional[float] = None
    debt_to_equity: Optional[float] = None
    data_freshness: str = "UNKNOWN"


class MultibaggerListResponse(BaseModel):
    results: list[MultibaggerResultResponse]
    total: int
    min_tier: str
    as_of: datetime


# ---------------------------------------------------------------------------
# R16: Backtesting Engine
# ---------------------------------------------------------------------------

class BacktestConfigRequest(BaseModel):
    strategy: str = "SMA_CROSSOVER"     # SMA_CROSSOVER / RSI_MEAN_REVERT / MACD_SIGNAL
    initial_capital: float = 10_000_000.0
    fee_pct: float = 0.0015
    # SMA params
    sma_fast: int = 50
    sma_slow: int = 200
    # RSI params
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    # MACD params
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal_period: int = 9

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        allowed = {"SMA_CROSSOVER", "RSI_MEAN_REVERT", "MACD_SIGNAL"}
        if v.upper() not in allowed:
            raise ValueError(f"strategy harus salah satu dari: {allowed}")
        return v.upper()

    @field_validator("initial_capital")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("initial_capital harus positif")
        return v


class EquityPointResponse(BaseModel):
    date: date
    equity: float
    drawdown_pct: float


class BacktestTradeResponse(BaseModel):
    entry_date: date
    exit_date: Optional[date] = None
    entry_price: float
    exit_price: Optional[float] = None
    shares: float
    pnl: float
    pnl_pct: float
    is_open: bool


class BacktestResultResponse(BaseModel):
    symbol: str
    strategy: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    sharpe_ratio: Optional[float] = None
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: Optional[float] = None
    bars_used: int
    equity_curve: list[EquityPointResponse]
    trades: list[BacktestTradeResponse]
    warnings: list[str]
    disclaimer: str = (
        "Hasil backtest berdasarkan data historis dan tidak menjamin performa masa depan. "
        "Bukan merupakan nasihat investasi."
    )


# ---------------------------------------------------------------------------
# R17: Global Macro Integration
# ---------------------------------------------------------------------------

class MacroRefreshResponse(BaseModel):
    inserted: int
    skipped: int
    series_fetched: list[str]
    errors: list[str]
    as_of: datetime


class YieldCurveResponse(BaseModel):
    signal: str                        # NORMAL / FLAT / INVERTED
    spread_pct: Optional[float] = None
    treasury_10y: Optional[float] = None
    treasury_2y: Optional[float] = None
    notes: str
    as_of: datetime


class MacroImpactResponse(BaseModel):
    score: float                       # -1.0 → +1.0
    level: str                         # POSITIVE / NEUTRAL / NEGATIVE / SEVERE
    drivers: list[str]
    recommendations: list[str]
    yield_curve: Optional[YieldCurveResponse] = None
    fed_rate: Optional[float] = None
    bi_rate: Optional[float] = None
    usd_idr: Optional[float] = None
    as_of: datetime


class MacroObservationUpsertRequest(BaseModel):
    """Upsert satu observasi makro secara manual."""
    series_id: str
    observed_date: date
    value: Optional[float] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# R18: Swing Trade Monitor
# ---------------------------------------------------------------------------

class SwingSetupResponse(BaseModel):
    instrument_id: str
    symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    exchange: Optional[str] = None
    as_of: date
    setup_type: str                    # BREAKOUT / PULLBACK / NO_SETUP
    strength: str                      # STRONG / MODERATE / WEAK
    current_price: float
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss_price: Optional[float] = None
    target_price: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    atr_14: Optional[float] = None
    resistance_level: Optional[float] = None
    support_level: Optional[float] = None
    rsi_14: Optional[float] = None
    volume_confirmation: bool = False
    notes: list[str] = []
    warnings: list[str] = []
    disclaimer: str = (
        "Setup swing trade ini bersifat informatif. "
        "Bukan rekomendasi transaksi. Keputusan sepenuhnya tanggung jawab pengguna."
    )


class SwingScreenResponse(BaseModel):
    setups: list[SwingSetupResponse]
    total: int
    setup_type_filter: Optional[str] = None
    min_strength: str
    as_of: datetime


# ---------------------------------------------------------------------------
# R19: Alert & Notification Engine
# ---------------------------------------------------------------------------

VALID_RULE_TYPES = {
    "price_above", "price_below",
    "pct_change_1d_above", "pct_change_1d_below",
    "rsi_above", "rsi_below",
    "swing_breakout", "swing_pullback",
    "macro_inverted",
}


class AlertRuleCreateRequest(BaseModel):
    rule_type: str
    canonical_symbol: Optional[str] = None      # None untuk rule global (mis. macro_inverted)
    threshold_value: Optional[float] = None
    cooldown_hours: int = 24
    webhook_url: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("rule_type")
    @classmethod
    def validate_rule_type(cls, v: str) -> str:
        if v.lower() not in VALID_RULE_TYPES:
            raise ValueError(f"rule_type tidak valid. Pilihan: {sorted(VALID_RULE_TYPES)}")
        return v.lower()

    @field_validator("cooldown_hours")
    @classmethod
    def validate_cooldown(cls, v: int) -> int:
        if v < 1 or v > 8760:
            raise ValueError("cooldown_hours harus antara 1–8760")
        return v


class AlertRuleResponse(BaseModel):
    id: str
    rule_type: str
    canonical_symbol: Optional[str] = None
    threshold_value: Optional[float] = None
    cooldown_hours: int
    is_active: bool
    fire_count: int
    last_fired_at: Optional[datetime] = None
    webhook_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AlertFiredResponse(BaseModel):
    rule_id: str
    rule_type: str
    symbol: Optional[str] = None
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    fired_at: datetime
    dedup_key: str
    webhook_sent: bool = False


class AlertEvalResponse(BaseModel):
    rules_checked: int
    alerts_fired: int
    alerts_skipped_cooldown: int
    fired: list[AlertFiredResponse]
    as_of: datetime


# ---------------------------------------------------------------------------
# R20 — Watchlist & Price Target
# ---------------------------------------------------------------------------

class WatchlistCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None


class WatchlistItemAddRequest(BaseModel):
    canonical_symbol: str
    notes: Optional[str] = None
    price_target: Optional[float] = None
    target_note: Optional[str] = None
    cost_basis: Optional[float] = None
    alert_on_target: bool = False


class WatchlistItemUpdateRequest(BaseModel):
    notes: Optional[str] = None
    price_target: Optional[float] = None
    target_note: Optional[str] = None
    cost_basis: Optional[float] = None
    alert_on_target: Optional[bool] = None


class WatchlistItemResponse(BaseModel):
    id: str
    watchlist_id: str
    instrument_id: str
    canonical_symbol: str
    company_name: Optional[str] = None
    exchange: Optional[str] = None
    notes: Optional[str] = None
    price_target: Optional[float] = None
    target_note: Optional[str] = None
    cost_basis: Optional[float] = None
    alert_on_target: bool = False
    last_price: Optional[float] = None
    pct_to_target: Optional[float] = None   # (target/last_price - 1) * 100
    pct_from_cost: Optional[float] = None   # (last_price/cost_basis - 1) * 100
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WatchlistResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    item_count: int = 0
    items: list[WatchlistItemResponse] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# R22 — Summary / Dashboard
# ---------------------------------------------------------------------------

class SummaryMacroBlock(BaseModel):
    yield_curve_signal: Optional[str] = None
    macro_impact_score: Optional[float] = None
    fed_funds_rate: Optional[float] = None
    as_of: Optional[str] = None


class SummarySwingItem(BaseModel):
    symbol: str
    setup_type: str
    strength: str
    rr_ratio: Optional[float] = None
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None


class SummaryAlertItem(BaseModel):
    rule_type: str
    symbol: Optional[str] = None
    message: str
    fired_at: datetime


class SummaryWatchItem(BaseModel):
    symbol: str
    last_price: Optional[float] = None
    price_target: Optional[float] = None
    pct_to_target: Optional[float] = None


class DashboardSummaryResponse(BaseModel):
    as_of: datetime
    macro: SummaryMacroBlock
    top_swing_setups: list[SummarySwingItem]
    recent_alerts: list[SummaryAlertItem]
    watchlist_near_target: list[SummaryWatchItem]


# ---------------------------------------------------------------------------
# Quick Position Entry
# ---------------------------------------------------------------------------

class QuickPositionRequest(BaseModel):
    """Tambah posisi via lot + harga rata-rata. Auto-create instrument jika perlu."""
    symbol: str                    # e.g., "BBCA" atau "IDX:BBCA"
    lots: int                      # 1 lot = 100 saham (IDX)
    avg_price: float               # harga rata-rata beli per saham (IDR)
    trade_date: Optional[date] = None  # default: hari ini
    fee: float = 0.0
    notes: Optional[str] = None

    @field_validator("lots")
    @classmethod
    def validate_lots(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Lot harus > 0")
        return v

    @field_validator("avg_price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Harga harus > 0")
        return v


class QuickPositionResponse(BaseModel):
    trade_id: str
    canonical_symbol: str
    company_name: Optional[str]
    lots: int
    shares: int
    avg_price: float
    total_cost: float
    trade_date: date
    price_refresh_triggered: bool


class EditPositionRequest(BaseModel):
    """Request edit posisi — ubah lot dan/atau harga rata-rata."""
    lots: int = Field(..., gt=0, description="Jumlah lot baru (1 lot = 100 saham)")
    avg_price: float = Field(..., gt=0, description="Harga rata-rata baru per saham")
    trade_date: Optional[date] = None
    notes: Optional[str] = None


class EditPositionResponse(BaseModel):
    canonical_symbol: str
    company_name: Optional[str]
    lots: int
    shares: int
    avg_price: float
    total_cost: float
    trade_date: date


# ---------------------------------------------------------------------------
# FREE-20 — Scheduler job history
# ---------------------------------------------------------------------------

class JobRunRow(BaseModel):
    job_name: str
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    duration_ms: Optional[int]
    summary: dict
    error: Optional[str]


class JobHistoryResponse(BaseModel):
    jobs: list[JobRunRow]
    total_jobs_known: int
    as_of: datetime


# ---------------------------------------------------------------------------
# FREE-21 — Platform health summary
# ---------------------------------------------------------------------------

class FreshnessHealthRow(BaseModel):
    total_bars: int
    fresh_bars: int
    stale_bars: int
    fresh_pct: float
    score: int


class GapsHealthRow(BaseModel):
    critical_count: int
    warning_count: int
    score: int


class QuotaHealthRow(BaseModel):
    exhausted_providers: list[str]
    score: int


class JobsHealthRow(BaseModel):
    total_known: int
    error_count: int
    last_error_job: Optional[str]
    score: int


class PlatformHealthResponse(BaseModel):
    overall_score: int
    grade: str
    freshness: FreshnessHealthRow
    gaps: GapsHealthRow
    quota: QuotaHealthRow
    jobs: JobsHealthRow
    computed_at: datetime


# ---------------------------------------------------------------------------
# FREE-22 — Stale instruments list
# ---------------------------------------------------------------------------

class StaleInstrumentRow(BaseModel):
    instrument_id: str
    canonical_symbol: str
    exchange: str
    stale_count: int
    fresh_count: int
    total_count: int
    stale_pct: float
    last_fresh_date: Optional[str]


class StaleInstrumentsResponse(BaseModel):
    instruments: list[StaleInstrumentRow]
    total_instruments: int
    total_stale_bars: int
    ran_at: datetime


# ---------------------------------------------------------------------------
# FREE-25: Batch instrument refresh
# ---------------------------------------------------------------------------

class BatchRefreshItemResult(BaseModel):
    canonical_symbol: str
    status: str           # ok | no_data | error | not_found
    bars_added: int = 0
    provider_used: Optional[str] = None
    message: Optional[str] = None


class BatchRefreshResponse(BaseModel):
    results: list[BatchRefreshItemResult]
    total_requested: int
    succeeded: int
    failed: int
    total_bars_added: int
    ran_at: datetime


# ---------------------------------------------------------------------------
# FREE-26: Provider success rate
# ---------------------------------------------------------------------------

class ProviderSuccessRow(BaseModel):
    provider_name: str
    date_str: str
    calls_succeeded: int
    calls_failed: int
    total_calls: int
    success_rate: float
    bars_fetched: int
    last_success_at: Optional[datetime]
    last_failure_at: Optional[datetime]
    last_error: Optional[str]


class ProviderSuccessResponse(BaseModel):
    providers: list[ProviderSuccessRow]
    as_of: datetime


# ---------------------------------------------------------------------------
# FREE-27: Coverage by sector/exchange
# ---------------------------------------------------------------------------

class ExchangeCoverageRow(BaseModel):
    exchange: str
    total_instruments: int
    instruments_with_fresh: int
    fresh_bars: int
    stale_bars: int
    total_bars: int
    fresh_pct: float


class SectorCoverageRow(BaseModel):
    sector: str           # "Unknown" jika NULL
    exchange: str
    instrument_count: int
    fresh_bars: int
    stale_bars: int
    total_bars: int
    fresh_pct: float


class CoverageBySectorResponse(BaseModel):
    by_exchange: list[ExchangeCoverageRow]
    by_sector: list[SectorCoverageRow]
    checked_at: datetime
