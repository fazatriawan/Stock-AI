/**
 * Typed API client untuk Stock Intelligence backend.
 * Semua angka dari backend harus disertai sumber — jangan tampilkan angka tanpa provenance.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
    throw new Error(err?.error?.message ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Types (mirror dari backend schemas)
// ---------------------------------------------------------------------------

export interface Instrument {
  id: string;
  canonical_symbol: string;
  local_symbol: string;
  exchange: string;
  country: string;
  currency: string;
  timezone: string;
  asset_type: string;
  sector: string | null;
  industry: string | null;
  company_name: string | null;
  status: string;
}

export interface PriceBar {
  session_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  adj_close: number | null;
  volume: number | null;
  provider: string;
  is_adjusted: boolean;
}

export interface TechnicalSnapshot {
  instrument_id: string;
  as_of: string;
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  atr_14: number | null;
  above_sma_20: boolean | null;
  above_sma_50: boolean | null;
  above_sma_200: boolean | null;
  golden_cross: boolean | null;
  return_1d: number | null;
  return_5d: number | null;
  return_20d: number | null;
  high_52w: number | null;
  low_52w: number | null;
  percentile_52w: number | null;
  volume_ratio_20: number | null;
  bars_available: number;
  sufficient_data: boolean;
  missing_indicators: string[];
}

export interface FundamentalSnapshot {
  instrument_id: string;
  as_of: string;
  sector: string | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  roe: number | null;
  eps: number | null;
  revenue: number | null;
  net_income: number | null;
  market_cap: number | null;
  dividend_yield: number | null;
  nim: number | null;
  npl_gross: number | null;
  car: number | null;
  metrics_available: string[];
  metrics_missing: string[];
  data_freshness: string;
  period_end: string | null;
}

export interface StockOverview {
  instrument: Instrument;
  last_price: number | null;
  last_price_date: string | null;
  price_provider: string | null;
  price_stale: boolean;
  technical: TechnicalSnapshot | null;
  fundamental: FundamentalSnapshot | null;
  as_of: string;
}

export interface FactorScores {
  fundamental: number | null;
  valuation: number | null;
  technical: number | null;
  macro_policy: number | null;
  risk_quality: number | null;
  events_news: number | null;
  ownership_flows: number | null;
  composite: number;
  coverage: number;
}

export interface Recommendation {
  instrument_id: string;
  canonical_symbol: string;
  as_of: string;
  action: "BUY" | "ADD_CANDIDATE" | "HOLD" | "TRIM_CANDIDATE" | "SELL" | "WAIT" | "INSUFFICIENT_DATA";
  urgency: "NORMAL" | "REVIEW_NOW";
  horizon: string;
  hard_gate_status: string;
  hard_gate_reason: string | null;
  factor_scores: FactorScores;
  evidence_confidence: "LOW" | "MEDIUM" | "HIGH";
  owned: boolean;
  bull_thesis: string[];
  bear_case: string[];
  conditions_to_buy: string[];
  conditions_to_sell: string[];
  invalidation_triggers: string[];
  data_gaps: string[];
  changed_from: string | null;
  human_approval_required: boolean;
  ai_enriched: boolean;
  ai_macro_context: string | null;
  ai_identified_risks: string[];
  ai_model: string | null;
  disclaimer: string;
}

export interface ProviderHealth {
  provider: string;
  status: "OK" | "DEGRADED" | "DOWN" | "UNKNOWN";
  last_success: string | null;
  last_error: string | null;
  notes: string | null;
}

export interface DataHealth {
  providers: ProviderHealth[];
  checked_at: string;
}

export interface DataProvider {
  provider: string;
  health_status: "OK" | "DEGRADED" | "DOWN" | "UNKNOWN";
  license_status: "FREE_PERSONAL" | "PAID" | "RESTRICTED" | "UNKNOWN";
  access_status: "ACTIVE" | "INACTIVE" | "NOT_CONFIGURED" | "QUOTA_EXHAUSTED" | "LICENSE_BLOCKED";
  cost: string;
  datasets: string[];
  granularity: string;
  freshness_policy: string;
  last_success: string | null;
  last_error: string | null;
  notes: string | null;
}

export interface DataProvidersResponse {
  providers: DataProvider[];
  checked_at: string;
}

export interface CSVImportResult {
  inserted: number;
  skipped_duplicate: number;
  skipped_existing_source: boolean;
  parse_errors: string[];
  source_id: string | null;
}

export interface FreshnessBreakdown {
  status: string;
  count: number;
}

export interface InstrumentFreshness {
  instrument_id: string;
  total_bars: number;
  fresh_bars: number;
  stale_bars: number;
  other_bars: number;
  data_quality_pct: number;
  last_fresh_date: string | null;
  last_bar_date: string | null;
  breakdown: FreshnessBreakdown[];
}

export interface CoverageStatus {
  fresh: number;
  stale: number;
  unavailable: number;
  quota_exhausted: number;
  other: number;
  total: number;
  stale_pct: number;
  unavailable_instruments: number;
  quota_instruments: number;
}

export interface GapReportRow {
  instrument_id: string;
  canonical_symbol: string;
  exchange: string;
  bar_count: number;
  expected_bars: number;
  gap_pct: number;
  first_date: string;
  last_date: string;
  history_days: number;
  severity: "CRITICAL" | "WARNING" | "OK";
}

export interface DataGapsStatus {
  reports: GapReportRow[];
  instruments_checked: number;
  with_gaps: number;
  ran_at: string;
}

export interface HealGapsResult {
  instruments_found: number;
  instruments_healed: number;
  bars_added: number;
  errors: string[];
  ran_at: string;
}

export interface StockRefreshResult {
  symbol: string;
  status: "ok" | "no_data";
  provider_used: string | null;
  fallback_used: boolean;
  providers_tried: string[];
  bars_added: number;
  bars_skipped?: number;
  gap_pct_before: number | null;
  gap_pct_after: number | null;
  message?: string;
  date_range?: { start: string; end: string };
}

export interface ProviderQuotaRow {
  provider_name: string;
  calls_today: number;
  quota_per_day: number | null;
  quota_exhausted: boolean;
  date_str: string;
}

export interface ProviderQuotaStatus {
  providers: ProviderQuotaRow[];
  total_calls_today: number;
  as_of: string;
}

export interface MarketStatus {
  exchange: string;
  timezone: string;
  is_trading_day: boolean;
  is_eod_data_ready: boolean;
  session_date: string;
  as_of: string;
}

// FREE-22 — Stale instruments list
export interface StaleInstrumentRow {
  instrument_id: string;
  canonical_symbol: string;
  exchange: string;
  stale_count: number;
  fresh_count: number;
  total_count: number;
  stale_pct: number;
  last_fresh_date: string | null;
}

export interface StaleInstrumentsStatus {
  instruments: StaleInstrumentRow[];
  total_instruments: number;
  total_stale_bars: number;
  ran_at: string;
}

// FREE-21 — Platform health summary
export interface PlatformHealthSummary {
  overall_score: number;
  grade: string;
  freshness: {
    total_bars: number;
    fresh_bars: number;
    stale_bars: number;
    fresh_pct: number;
    score: number;
  };
  gaps: {
    critical_count: number;
    warning_count: number;
    score: number;
  };
  quota: {
    exhausted_providers: string[];
    score: number;
  };
  jobs: {
    total_known: number;
    error_count: number;
    last_error_job: string | null;
    score: number;
  };
  computed_at: string;
}

// FREE-20 — Scheduler job history
export interface JobRunRow {
  job_name: string;
  started_at: string;
  finished_at: string | null;
  status: string; // "running" | "ok" | "error"
  duration_ms: number | null;
  summary: Record<string, unknown>;
  error: string | null;
}

export interface JobHistoryStatus {
  jobs: JobRunRow[];
  total_jobs_known: number;
  as_of: string;
}

// ---------------------------------------------------------------------------
// Portfolio types (Phase 1)
// ---------------------------------------------------------------------------

export interface Trade {
  id: string;
  portfolio_id: string;
  instrument_id: string;
  canonical_symbol: string;
  company_name: string | null;
  trade_date: string;
  side: "BUY" | "SELL";
  shares: number;
  lots: number;
  price: number;
  fee: number;
  tax: number;
  currency: string;
  source_broker: string | null;
  notes: string | null;
  created_at: string | null;
}

export interface TradeCreateRequest {
  canonical_symbol: string;
  trade_date: string;
  side: "BUY" | "SELL";
  shares: number;
  price: number;
  fee?: number;
  tax?: number;
  currency?: string;
  source_broker?: string;
  notes?: string;
}

export interface QuickPositionRequest {
  symbol: string;
  lots: number;
  avg_price: number;
  trade_date?: string;
  fee?: number;
  notes?: string;
}

export interface QuickPositionResponse {
  trade_id: string;
  canonical_symbol: string;
  company_name: string | null;
  lots: number;
  shares: number;
  avg_price: number;
  total_cost: number;
  trade_date: string;
  price_refresh_triggered: boolean;
}

export interface Position {
  instrument_id: string;
  canonical_symbol: string;
  company_name: string | null;
  exchange: string;
  currency: string;
  sector: string | null;
  shares: number;
  lots: number;
  avg_cost: number;
  total_cost: number;
  current_price: number | null;
  current_price_date: string | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  weight: number;
  trade_count: number;
  first_buy_date: string | null;
  last_trade_date: string | null;
}

export interface PortfolioSummary {
  portfolio_id: string;
  portfolio_name: string;
  base_currency: string;
  as_of: string;
  total_invested: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  positions: Position[];
  sector_weights: Record<string, number>;
  concentration_warnings: string[];
  trade_count: number;
}

export interface PortfolioSeedResult {
  message: string;
  portfolio_id: string;
  created: number;
  skipped: number;
  errors: string[];
}

// ---------------------------------------------------------------------------
// Portfolio Intelligence types (Phase 3)
// ---------------------------------------------------------------------------

export interface ConcentrationRisk {
  symbol: string;
  weight: number;
  severity: "NORMAL" | "OVERWEIGHT" | "SEVERELY_OVERWEIGHT";
  message: string;
}

export interface SectorRisk {
  sector: string;
  weight: number;
  severity: "NORMAL" | "CONCENTRATED";
  message: string;
}

export interface PortfolioHealth {
  health_score: number;
  grade: "EXCELLENT" | "GOOD" | "FAIR" | "POOR";
  position_count: number;
  diversification_score: number;
  concentration_risks: ConcentrationRisk[];
  sector_risks: SectorRisk[];
  largest_position_symbol: string | null;
  largest_position_weight: number;
  total_invested: number;
  total_market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  diversification_component: number;
  concentration_component: number;
  pnl_component: number;
  warnings: string[];
  recommendations: string[];
}

export interface LossScenario {
  scenario: "CUT_LOSS" | "PARTIAL_CUT" | "HOLD_WAIT" | "AVERAGE_DOWN" | "STOP_LOSS";
  label: string;
  description: string;
  projected_loss_idr: number;
  projected_loss_pct: number;
  remaining_exposure_idr: number;
  breakeven_price: number | null;
  pros: string[];
  cons: string[];
  risk_level: "LOW" | "MEDIUM" | "HIGH";
}

export interface LossPosition {
  canonical_symbol: string;
  company_name: string | null;
  shares: number;
  lots: number;
  avg_cost: number;
  current_price: number;
  total_cost: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  scenarios: LossScenario[];
  suggested_scenario: string;
  suggested_reason: string;
}

export interface LossAnalysis {
  loss_positions: LossPosition[];
  total_loss_positions: number;
  total_unrealized_loss_idr: number;
  as_of: string;
}

// ---------------------------------------------------------------------------
// Daily Intelligence & Journal types (Phase 5)
// ---------------------------------------------------------------------------

export interface DailyPositionBrief {
  canonical_symbol: string;
  company_name: string | null;
  lots: number;
  avg_cost: number;
  current_price: number | null;
  unrealized_pnl_pct: number | null;
  weight: number;
  action: string | null;
  urgency: string | null;
  data_stale: boolean;
}

export interface DailyIntelligence {
  as_of: string;
  market_open: boolean;
  total_positions: number;
  total_market_value: number;
  unrealized_pnl_pct: number;
  positions: DailyPositionBrief[];
  alerts: string[];
  data_freshness: "FRESH" | "STALE" | "PARTIAL";
}

export interface JournalEntry {
  id: string;
  canonical_symbol: string;
  decision_date: string;
  action: "BUY" | "SELL" | "HOLD" | "WATCH";
  rationale: string;
  thesis: string | null;
  invalidation: string | null;
  price_at_decision: number | null;
  outcome: "CORRECT" | "INCORRECT" | "PENDING" | null;
  outcome_notes: string | null;
  reviewed_at: string | null;
  created_at: string | null;
}

export interface JournalCreateRequest {
  canonical_symbol: string;
  decision_date: string;
  action: "BUY" | "SELL" | "HOLD" | "WATCH";
  rationale: string;
  thesis?: string;
  invalidation?: string;
  price_at_decision?: number;
}

// ---------------------------------------------------------------------------
// Rebalance simulator types (Phase 4)
// ---------------------------------------------------------------------------

export interface TargetAllocation {
  canonical_symbol: string;
  company_name: string | null;
  sector: string | null;
  current_lots: number;
  current_weight: number;
  target_weight: number;
  current_market_value: number;
  target_market_value: number;
  delta_value: number;
  delta_lots: number;
  action: "BUY" | "SELL" | "HOLD";
  note: string;
}

export interface RebalanceSimulation {
  total_portfolio_value: number;
  positions_count: number;
  allocations: TargetAllocation[];
  buy_actions: number;
  sell_actions: number;
  hold_actions: number;
  total_buy_value: number;
  total_sell_value: number;
  net_cash_needed: number;
  disclaimer: string;
}

export interface AllocationSuggestion {
  canonical_symbol: string;
  company_name: string | null;
  sector: string | null;
  current_weight: number;
  suggested_new_amount: number;
  suggested_lots: number;
  rationale: string;
  priority: number;
}

export interface CapitalAllocationPlan {
  new_capital: number;
  total_positions: number;
  suggestions: AllocationSuggestion[];
  undiversified_warning: string | null;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Import pipeline types (Phase 2)
// ---------------------------------------------------------------------------

export interface ParsedTradePreview {
  row_number: number;
  canonical_symbol: string;
  trade_date: string;
  side: "BUY" | "SELL";
  lots: number;
  shares: number;
  price: number;
  fee: number;
  tax: number;
  currency: string;
  source_broker: string;
  fingerprint: string;
  status: "OK" | "WARNING" | "ERROR";
  warnings: string[];
  errors: string[];
}

export interface ImportPreviewResponse {
  broker_format: string;
  total_rows: number;
  valid_count: number;
  error_count: number;
  duplicate_count: number;
  trades: ParsedTradePreview[];
  parse_errors: string[];
  warnings: string[];
}

export interface ImportConfirmResponse {
  message: string;
  created: number;
  skipped_duplicates: number;
  skipped_errors: number;
  errors: string[];
}

// ---------------------------------------------------------------------------
// Phase D types — Decisions / Screener / Performance
// ---------------------------------------------------------------------------

export type DecisionSummary = {
  instrument_id: string;
  canonical_symbol: string;
  company_name: string | null;
  sector: string | null;
  action: string;
  urgency: string;
  composite_score: number;
  evidence_confidence: string;
  hard_gate_status: string;
  hard_gate_reason: string | null;
  owned: boolean;
  portfolio_weight: number | null;
  current_price: number | null;
  bull_thesis: string[];
  bear_case: string[];
  data_gaps: string[];
  factor_scores: Record<string, number | null>;
};

export type DecisionList = {
  decisions: DecisionSummary[];
  total: number;
  action_counts: Record<string, number>;
  generated_at: string;
};

export type ScreenerResult = {
  instrument_id: string;
  canonical_symbol: string;
  company_name: string | null;
  sector: string | null;
  exchange: string | null;
  current_price: number | null;
  action: string;
  composite_score: number;
  evidence_confidence: string;
  pe_ratio: number | null;
  pb_ratio: number | null;
  roe: number | null;
  dividend_yield: number | null;
  rsi_14: number | null;
  above_sma_200: boolean | null;
  return_20d: number | null;
  data_freshness: string;
};

export type ScreenerList = {
  results: ScreenerResult[];
  total: number;
  filters_applied: Record<string, unknown>;
  as_of: string;
};

export type ScreenerFilters = {
  sector?: string;
  exchange?: string;
  min_roe?: number;
  max_pe?: number;
  min_pe?: number;
  min_composite?: number;
  action?: string;
  limit?: number;
};

export type ReverseScenario = {
  target_multiple: number;
  horizon_years: number;
  required_eps_cagr_constant_pe_pct: number;
  required_eps_cagr_rerating_pct: number | null;
  assumed_annual_dilution_pct: number;
  downside_risk_note: string;
};

export type MultibaggerResult = {
  instrument_id: string;
  canonical_symbol: string;
  company_name: string | null;
  sector: string | null;
  exchange: string | null;
  current_price: number | null;
  score: {
    instrument_id: string;
    symbol: string;
    tier: string;
    total_score: number;
    components: Array<{ name: string; score: number; max_score: number; notes: string }>;
    strengths: string[];
    concerns: string[];
    data_completeness: number;
    pipelines_matched: string[];
    reverse_scenarios: ReverseScenario[];
  };
  pe_ratio: number | null;
  roe: number | null;
  net_margin: number | null;
  revenue_growth_1y: number | null;
  debt_to_equity: number | null;
  data_freshness: string;
};

export type MultibaggerList = {
  results: MultibaggerResult[];
  total: number;
  min_tier: string;
  as_of: string;
};

export type PositionAttributionItem = {
  symbol: string;
  sector: string | null;
  weight: number;
  total_return_pct: number;
  price_return_pct: number;
  dividend_contribution_pct: number;
  cost_drag_pct: number;
  benchmark_effect_pct: number;
  sector_excess_pct: number;
  stock_specific_alpha_pct: number;
  baseline_excess_pct: number;
  attribution_caveat: string;
};

export type PortfolioAttribution = {
  portfolio_total_return_pct: number;
  benchmark_return_pct: number;
  portfolio_excess_return_pct: number;
  weighted_sector_effect_pct: number;
  weighted_stock_alpha_pct: number;
  weighted_dividend_pct: number;
  weighted_cost_drag_pct: number;
  positions: PositionAttributionItem[];
  caveat: string;
  as_of: string;
};

export type EquityDataPoint = {
  date: string;
  portfolio_value: number;
  invested: number;
  pnl_pct: number;
};

export type PositionContribution = {
  canonical_symbol: string;
  company_name: string | null;
  total_cost: number;
  current_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  portfolio_weight: number;
};

export type PortfolioPerformance = {
  equity_curve: EquityDataPoint[];
  total_return_pct: number;
  total_invested: number;
  current_value: number;
  unrealized_pnl: number;
  position_contributions: PositionContribution[];
  best_position: PositionContribution | null;
  worst_position: PositionContribution | null;
  as_of: string;
};

// ---------------------------------------------------------------------------
// Macro
// ---------------------------------------------------------------------------

export type MacroObservation = {
  series_id: string;
  label: string;
  value: number | null;
  observed_date: string;
  released_at: string | null;
};

export type MacroSnapshot = {
  observations: MacroObservation[];
  total_series: number;
  as_of: string;
};

export type PolicyEvent = {
  id: string;
  event_type: string;
  title: string;
  summary: string | null;
  country: string | null;
  affected_sectors: string[];
  effective_date: string | null;
  published_at: string | null;
  policy_stage: string | null;
  materiality: string | null;
  company_impacts: Array<{
    canonical_symbol: string;
    company_name: string | null;
    sign: string;
    exposure: string | null;
    mechanism: string | null;
    confidence: string | null;
  }>;
};

export type PolicyEventList = {
  events: PolicyEvent[];
  total: number;
  as_of: string;
};

export type PolicyEventCreateRequest = {
  event_type: string;
  title: string;
  summary?: string;
  country?: string;
  affected_sectors?: string[];
  effective_date?: string;
  published_at?: string;
  policy_stage?: string;
  materiality?: string;
};

// ---------------------------------------------------------------------------
// Research Notebook
// ---------------------------------------------------------------------------

export type ResearchNote = {
  id: string;
  title: string;
  body: string;
  canonical_symbol: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type NoteCreateRequest = {
  title: string;
  body?: string;
  canonical_symbol?: string;
  tags?: string[];
};

export type NoteUpdateRequest = {
  title?: string;
  body?: string;
  canonical_symbol?: string;
  tags?: string[];
};

// ---------------------------------------------------------------------------
// R20 — Watchlist types
// ---------------------------------------------------------------------------

export type WatchlistItemResponse = {
  id: string;
  watchlist_id: string;
  instrument_id: string;
  canonical_symbol: string;
  company_name: string | null;
  exchange: string | null;
  notes: string | null;
  price_target: number | null;
  target_note: string | null;
  cost_basis: number | null;
  alert_on_target: boolean;
  last_price: number | null;
  pct_to_target: number | null;
  pct_from_cost: number | null;
  created_at: string | null;
};

export type WatchlistResponse = {
  id: string;
  name: string;
  description: string | null;
  item_count: number;
  items: WatchlistItemResponse[];
  created_at: string | null;
};

export type WatchlistItemAddRequest = {
  canonical_symbol: string;
  notes?: string;
  price_target?: number;
  target_note?: string;
  cost_basis?: number;
  alert_on_target?: boolean;
};

// ---------------------------------------------------------------------------
// R19 — Alert types
// ---------------------------------------------------------------------------

export type AlertRuleResponse = {
  id: string;
  rule_type: string;
  canonical_symbol: string | null;
  threshold_value: number | null;
  cooldown_hours: number;
  is_active: boolean;
  fire_count: number;
  last_fired_at: string | null;
  webhook_url: string | null;
  notes: string | null;
  created_at: string | null;
};

export type AlertRuleCreateRequest = {
  rule_type: string;
  canonical_symbol?: string;
  threshold_value?: number;
  cooldown_hours?: number;
  webhook_url?: string;
  notes?: string;
};

export type AlertFiredResponse = {
  rule_id: string;
  rule_type: string;
  symbol: string | null;
  message: string;
  value: number | null;
  threshold: number | null;
  fired_at: string;
  dedup_key: string;
  webhook_sent: boolean;
};

export type AlertEvalResponse = {
  rules_checked: number;
  alerts_fired: number;
  alerts_skipped_cooldown: number;
  fired: AlertFiredResponse[];
  as_of: string;
};

export type AlertHistoryItem = {
  id: string;
  event_type: string;
  materiality: string;
  dedup_key: string;
  payload: Record<string, unknown> | null;
  delivered_at: string | null;
  acknowledged_at: string | null;
  created_at: string | null;
};

// ---------------------------------------------------------------------------
// R22 — Summary types
// ---------------------------------------------------------------------------

export type DashboardSummaryResponse = {
  as_of: string;
  macro: {
    yield_curve_signal: string | null;
    macro_impact_score: number | null;
    fed_funds_rate: number | null;
    as_of: string | null;
  };
  top_swing_setups: {
    symbol: string;
    setup_type: string;
    strength: string;
    rr_ratio: number | null;
    entry_low: number | null;
    entry_high: number | null;
  }[];
  recent_alerts: {
    rule_type: string;
    symbol: string | null;
    message: string;
    fired_at: string;
  }[];
  watchlist_near_target: {
    symbol: string;
    last_price: number | null;
    price_target: number | null;
    pct_to_target: number | null;
  }[];
};

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const api = {
  markets: {
    status: () => apiFetch<MarketStatus[]>("/markets/status"),
  },
  instruments: {
    search: (q: string, limit = 20) =>
      apiFetch<{ results: Instrument[]; query: string; count: number }>(
        `/instruments/search?q=${encodeURIComponent(q)}&limit=${limit}`
      ),
    get: (symbol: string) => apiFetch<Instrument>(`/instruments/${symbol}`),
  },
  stocks: {
    prices: (symbol: string, range = "1y") =>
      apiFetch<{ instrument: Instrument; bars: PriceBar[]; count: number; provider: string; as_of: string }>(
        `/stocks/${symbol}/prices?range=${range}`
      ),
    overview: (symbol: string) => apiFetch<StockOverview>(`/stocks/${symbol}/overview`),
    analysis: (symbol: string) => apiFetch<Recommendation>(`/stocks/${symbol}/analysis`),
    refreshData: (symbol: string, daysBack = 365) =>
      apiFetch<StockRefreshResult>(`/stocks/${symbol}/data/refresh?days_back=${daysBack}`, { method: "POST" }),
    exportCsvUrl: (symbol: string, includeStale = false) =>
      `${API_BASE}/stocks/${symbol}/ohlcv/export?include_stale=${includeStale}`,
  },
  data: {
    health: () => apiFetch<DataHealth>("/data/health"),
    providers: () => apiFetch<DataProvidersResponse>("/data/providers"),
    freshness: (instrumentId: string) =>
      apiFetch<InstrumentFreshness>(`/data/freshness/${instrumentId}`),
    markStale: () =>
      apiFetch<{ marked_stale: number; cutoff_date: string; ran_at: string }>("/data/mark-stale", { method: "POST" }),
    refreshStale: () =>
      apiFetch<{ instruments_found: number; instruments_refreshed: number; bars_added: number; errors: string[] }>("/data/refresh-stale", { method: "POST" }),
    importCSV: (formData: FormData) =>
      apiFetch<CSVImportResult>("/data/import/csv", {
        method: "POST",
        body: formData,
        headers: {},  // let browser set multipart boundary
      }),
    coverage: () => apiFetch<CoverageStatus>("/data/coverage"),
    resetQuota: () =>
      apiFetch<{ bars_reset: number; ran_at: string }>("/data/reset-quota", { method: "POST" }),
    providerQuota: () => apiFetch<ProviderQuotaStatus>("/data/provider-quota"),
    gaps: (threshold = 10, minHistory = 30, limit = 50) =>
      apiFetch<DataGapsStatus>(`/data/gaps?threshold_pct=${threshold}&min_history=${minHistory}&limit=${limit}`),
    healGaps: (threshold = 10, minHistory = 30, limit = 20) =>
      apiFetch<HealGapsResult>(`/data/gaps/heal?threshold_pct=${threshold}&min_history=${minHistory}&limit=${limit}`, { method: "POST" }),
    staleInstruments: (limit = 50) =>
      apiFetch<StaleInstrumentsStatus>(`/data/stale-instruments?limit=${limit}`),
  },
  portfolio: {
    summary: () => apiFetch<PortfolioSummary>("/portfolio"),
    trades: () => apiFetch<Trade[]>("/portfolio/trades"),
    addTrade: (body: TradeCreateRequest) =>
      apiFetch<Trade>("/portfolio/trades", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    deleteTrade: (id: string) =>
      apiFetch<void>(`/portfolio/trades/${id}`, { method: "DELETE" }),
    seed: () =>
      apiFetch<PortfolioSeedResult>("/portfolio/seed", { method: "POST" }),
    importPreview: (formData: FormData) =>
      apiFetch<ImportPreviewResponse>("/portfolio/import/preview", {
        method: "POST",
        body: formData,
        headers: {},  // biarkan browser set Content-Type dengan boundary
      }),
    importConfirm: (trades: ParsedTradePreview[], skipDuplicates = true) =>
      apiFetch<ImportConfirmResponse>("/portfolio/import/confirm", {
        method: "POST",
        body: JSON.stringify({ trades, skip_duplicates: skipDuplicates }),
      }),
    quickAddPosition: (body: QuickPositionRequest) =>
      apiFetch<QuickPositionResponse>("/portfolio/positions/quick", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    deletePosition: (symbol: string) =>
      apiFetch<{ deleted_trades: number; message: string }>(`/portfolio/positions/${encodeURIComponent(symbol)}`, {
        method: "DELETE",
      }),
    refreshPrices: () =>
      apiFetch<{ triggered: number; symbols: string[]; message: string }>("/portfolio/prices/refresh", {
        method: "POST",
      }),
    editPosition: (symbol: string, body: { lots: number; avg_price: number; trade_date?: string; notes?: string }) =>
      apiFetch<{ canonical_symbol: string; lots: number; shares: number; avg_price: number; total_cost: number; trade_date: string }>(`/portfolio/positions/${encodeURIComponent(symbol)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    health: () => apiFetch<PortfolioHealth>("/portfolio/health"),
    lossAnalysis: () => apiFetch<LossAnalysis>("/portfolio/loss"),
    simulateRebalance: (targetWeights: Record<string, number> = {}, newCapital = 0) =>
      apiFetch<RebalanceSimulation>("/portfolio/simulate/rebalance", {
        method: "POST",
        body: JSON.stringify({ target_weights: targetWeights, new_capital: newCapital }),
      }),
    planAllocation: (newCapital: number) =>
      apiFetch<CapitalAllocationPlan>("/portfolio/simulate/allocate", {
        method: "POST",
        body: JSON.stringify({ new_capital: newCapital }),
      }),
  },
  daily: {
    intelligence: () => apiFetch<DailyIntelligence>("/daily"),
  },
  journal: {
    list: (symbol?: string, action?: string) => {
      const params = new URLSearchParams();
      if (symbol) params.set("symbol", symbol);
      if (action) params.set("action", action);
      const qs = params.toString();
      return apiFetch<JournalEntry[]>(`/journal${qs ? `?${qs}` : ""}`);
    },
    create: (body: JournalCreateRequest) =>
      apiFetch<JournalEntry>("/journal", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    review: (id: string, outcome: string, notes?: string) =>
      apiFetch<JournalEntry>(`/journal/${id}/review`, {
        method: "PATCH",
        body: JSON.stringify({ outcome, outcome_notes: notes }),
      }),
    delete: (id: string) =>
      apiFetch<void>(`/journal/${id}`, { method: "DELETE" }),
  },
  decisions: {
    list: (action?: string, includeWatchlist = true) => {
      const params = new URLSearchParams();
      if (action) params.set("action", action);
      params.set("include_watchlist", String(includeWatchlist));
      return apiFetch<DecisionList>(`/decisions?${params.toString()}`);
    },
  },
  screener: {
    screen: (filters: ScreenerFilters = {}) => {
      const params = new URLSearchParams();
      if (filters.sector) params.set("sector", filters.sector);
      if (filters.exchange) params.set("exchange", filters.exchange);
      if (filters.min_roe != null) params.set("min_roe", String(filters.min_roe));
      if (filters.max_pe != null) params.set("max_pe", String(filters.max_pe));
      if (filters.min_pe != null) params.set("min_pe", String(filters.min_pe));
      if (filters.min_composite != null) params.set("min_composite", String(filters.min_composite));
      if (filters.action) params.set("action", filters.action);
      if (filters.limit) params.set("limit", String(filters.limit));
      return apiFetch<ScreenerList>(`/screener?${params.toString()}`);
    },
    multibagger: (filters: { sector?: string; exchange?: string; min_tier?: string; min_score?: number; limit?: number } = {}) => {
      const params = new URLSearchParams();
      if (filters.sector) params.set("sector", filters.sector);
      if (filters.exchange) params.set("exchange", filters.exchange);
      if (filters.min_tier) params.set("min_tier", filters.min_tier);
      if (filters.min_score != null) params.set("min_score", String(filters.min_score));
      if (filters.limit) params.set("limit", String(filters.limit));
      return apiFetch<MultibaggerList>(`/screener/multibagger?${params.toString()}`);
    },
  },
  performance: {
    get: (range = "6m") => apiFetch<PortfolioPerformance>(`/portfolio/performance?range=${range}`),
    attribution: (benchmarkReturnPct = 5.0) =>
      apiFetch<PortfolioAttribution>(`/portfolio/attribution?benchmark_return_pct=${benchmarkReturnPct}`),
  },
  macro: {
    snapshot: () => apiFetch<MacroSnapshot>("/macro/observations"),
    events: (params?: { materiality?: string; country?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.materiality) qs.set("materiality", params.materiality);
      if (params?.country) qs.set("country", params.country);
      if (params?.limit) qs.set("limit", String(params.limit));
      const q = qs.toString();
      return apiFetch<PolicyEventList>(`/macro/events${q ? `?${q}` : ""}`);
    },
    createEvent: (body: PolicyEventCreateRequest) =>
      apiFetch<PolicyEvent>("/macro/events", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
  notebook: {
    list: (params?: { symbol?: string; tag?: string; search?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.symbol) qs.set("symbol", params.symbol);
      if (params?.tag) qs.set("tag", params.tag);
      if (params?.search) qs.set("search", params.search);
      if (params?.limit) qs.set("limit", String(params.limit));
      const q = qs.toString();
      return apiFetch<ResearchNote[]>(`/notebook${q ? `?${q}` : ""}`);
    },
    get: (id: string) => apiFetch<ResearchNote>(`/notebook/${id}`),
    create: (body: NoteCreateRequest) =>
      apiFetch<ResearchNote>("/notebook", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    update: (id: string, body: NoteUpdateRequest) =>
      apiFetch<ResearchNote>(`/notebook/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    delete: (id: string) =>
      apiFetch<void>(`/notebook/${id}`, { method: "DELETE" }),
  },
  admin: {
    setupStatus: () =>
      apiFetch<{ instruments_loaded: number; price_bars: number; yfinance_enabled: boolean; is_ready: boolean }>("/admin/setup-status"),
    bootstrap: (useMock = false) =>
      apiFetch<{ message: string; instruments_loaded: number; ohlcv_job: string }>(`/admin/bootstrap?use_mock=${useMock}`, {
        method: "POST",
      }),
    bootstrapIDX: () =>
      apiFetch<{ status: string; message: string }>("/admin/bootstrap/idx", { method: "POST" }),
    bootstrapUS: () =>
      apiFetch<{ status: string; message: string }>("/admin/bootstrap/us", { method: "POST" }),
    resetQuotaTracker: () =>
      apiFetch<{ status: string; message: string; reset_at: string }>("/admin/quota-tracker/reset", { method: "POST" }),
    jobHistory: () =>
      apiFetch<JobHistoryStatus>("/admin/jobs"),
    healthSummary: () =>
      apiFetch<PlatformHealthSummary>("/admin/health-summary"),
  },

  // R20 — Watchlist
  watchlists: {
    list: () => apiFetch<WatchlistResponse[]>("/watchlists"),
    get: (id: string) => apiFetch<WatchlistResponse>(`/watchlists/${id}`),
    create: (body: { name: string; description?: string }) =>
      apiFetch<WatchlistResponse>("/watchlists", { method: "POST", body: JSON.stringify(body) }),
    delete: (id: string) => apiFetch<void>(`/watchlists/${id}`, { method: "DELETE" }),
    addItem: (watchlistId: string, body: WatchlistItemAddRequest) =>
      apiFetch<WatchlistItemResponse>(`/watchlists/${watchlistId}/items`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    updateItem: (watchlistId: string, itemId: string, body: Partial<WatchlistItemAddRequest>) =>
      apiFetch<WatchlistItemResponse>(`/watchlists/${watchlistId}/items/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    removeItem: (watchlistId: string, itemId: string) =>
      apiFetch<void>(`/watchlists/${watchlistId}/items/${itemId}`, { method: "DELETE" }),
  },

  // R19 — Alerts
  alerts: {
    listRules: (activeOnly = true) =>
      apiFetch<AlertRuleResponse[]>(`/alerts/rules?active_only=${activeOnly}`),
    createRule: (body: AlertRuleCreateRequest) =>
      apiFetch<AlertRuleResponse>("/alerts/rules", { method: "POST", body: JSON.stringify(body) }),
    deleteRule: (id: string) => apiFetch<void>(`/alerts/rules/${id}`, { method: "DELETE" }),
    evaluate: () => apiFetch<AlertEvalResponse>("/alerts/evaluate", { method: "POST" }),
    history: (limit = 50) => apiFetch<AlertHistoryItem[]>(`/alerts/history?limit=${limit}`),
  },

  // R22 — Summary
  summary: {
    get: () => apiFetch<DashboardSummaryResponse>("/summary"),
  },

  // Chat assistant
  chat: {
    send: (body: { message: string; history?: { role: string; content: string }[]; context?: Record<string, unknown> }) =>
      apiFetch<{ reply: string; model_used: string; skipped: boolean; skip_reason?: string }>("/chat", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
};
