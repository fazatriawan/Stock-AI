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
  action: "BUY" | "HOLD" | "SELL" | "WAIT" | "INSUFFICIENT_DATA";
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

export interface MarketStatus {
  exchange: string;
  timezone: string;
  is_trading_day: boolean;
  is_eod_data_ready: boolean;
  session_date: string;
  as_of: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const api = {
  markets: {
    status: () => apiFetch<MarketStatus[]>("/markets/status"),
  },
  instruments: {
    search: (q: string) =>
      apiFetch<{ results: Instrument[]; query: string; count: number }>(
        `/instruments/search?q=${encodeURIComponent(q)}`
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
  },
  data: {
    health: () => apiFetch<DataHealth>("/data/health"),
  },
  admin: {
    bootstrap: (useMock = true) =>
      apiFetch<{ message: string; instruments_loaded: number }>(`/admin/bootstrap?use_mock=${useMock}`, {
        method: "POST",
      }),
  },
};
