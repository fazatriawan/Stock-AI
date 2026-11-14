"use client";

import { useEffect, useRef, useState } from "react";
import { Search, DatabaseZap, RefreshCw, Download } from "lucide-react";
import { api, type StockOverview, type Recommendation, type InstrumentFreshness, type StockRefreshResult, type Instrument } from "@/lib/api";
import { StockOverviewCard } from "@/components/stock/StockOverviewCard";
import { RecommendationCard } from "@/components/stock/RecommendationCard";
import { TechnicalCard } from "@/components/stock/TechnicalCard";
import { FundamentalCard } from "@/components/stock/FundamentalCard";

function FreshnessChip({ freshness }: { freshness: InstrumentFreshness }) {
  const q = freshness.data_quality_pct;
  const isGood = q >= 95;
  const isMid = q >= 70 && q < 95;
  const color = isGood
    ? "text-emerald-400 border-emerald-800/40 bg-emerald-950/20"
    : isMid
    ? "text-amber-400 border-amber-800/40 bg-amber-950/20"
    : "text-red-400 border-red-800/40 bg-red-950/20";

  if (q >= 100) return null;  // semua FRESH — tidak perlu chip

  return (
    <div className={`inline-flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-lg border ${color}`}>
      <DatabaseZap size={11} />
      <span>Kualitas data: {q}%</span>
      {freshness.last_fresh_date && (
        <span className="opacity-70">· FRESH terakhir {freshness.last_fresh_date}</span>
      )}
    </div>
  );
}

export default function ExplorerPage() {
  const [query, setQuery] = useState("");
  const [overview, setOverview] = useState<StockOverview | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [freshness, setFreshness] = useState<InstrumentFreshness | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<StockRefreshResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Autocomplete state
  const [suggestions, setSuggestions] = useState<Instrument[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(-1);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  // Debounced search as user types
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await api.instruments.search(query.trim(), 8);
        setSuggestions(r.results);
        setShowSuggestions(r.results.length > 0);
        setActiveSuggestion(-1);
      } catch {
        setSuggestions([]);
        setShowSuggestions(false);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query]);

  async function handleRefresh() {
    if (!overview) return;
    setRefreshing(true);
    setRefreshResult(null);
    try {
      const r = await api.stocks.refreshData(overview.instrument.canonical_symbol);
      setRefreshResult(r);
      const [ov] = await Promise.all([api.stocks.overview(overview.instrument.canonical_symbol)]);
      setOverview(ov);
      api.data.freshness(ov.instrument.id).then(setFreshness).catch(() => {});
    } catch {
      // non-blocking
    } finally {
      setRefreshing(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setShowSuggestions(false);
    await searchTicker(query.trim());
  }

  async function searchTicker(ticker: string) {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    setOverview(null);
    setRecommendation(null);
    setFreshness(null);
    setRefreshResult(null);
    setShowSuggestions(false);

    try {
      const [ov, rec] = await Promise.all([
        api.stocks.overview(ticker),
        api.stocks.analysis(ticker),
      ]);
      setOverview(ov);
      setRecommendation(rec);
      api.data.freshness(ov.instrument.id).then(setFreshness).catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gagal memuat data");
    } finally {
      setLoading(false);
    }
  }

  function handleSuggestionClick(instr: Instrument) {
    setQuery(instr.canonical_symbol);
    setShowSuggestions(false);
    setSuggestions([]);
    searchTicker(instr.canonical_symbol);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveSuggestion((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveSuggestion((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && activeSuggestion >= 0) {
      e.preventDefault();
      handleSuggestionClick(suggestions[activeSuggestion]);
    } else if (e.key === "Escape") {
      setShowSuggestions(false);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Stock Explorer</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Cari ticker IDX (BBCA, BMRI) atau US (AAPL, MSFT) untuk melihat analisis
        </p>
      </div>

      {/* Search with autocomplete */}
      <form onSubmit={handleSearch} className="flex gap-2 max-w-md">
        <div className="relative flex-1" ref={wrapperRef}>
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 z-10" size={14} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
            placeholder="Cari ticker: BBCA, IDX:BMRI, AAPL..."
            autoComplete="off"
            className="w-full pl-9 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-gray-500"
          />

          {/* Autocomplete dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
              {suggestions.map((instr, idx) => (
                <button
                  key={instr.id}
                  type="button"
                  onMouseDown={(e) => { e.preventDefault(); handleSuggestionClick(instr); }}
                  onMouseEnter={() => setActiveSuggestion(idx)}
                  className={`w-full flex items-center justify-between px-3 py-2 text-left transition-colors ${
                    idx === activeSuggestion ? "bg-gray-700/70" : "hover:bg-gray-700/40"
                  }`}
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="text-sm font-mono text-gray-100 shrink-0">{instr.canonical_symbol}</span>
                    {instr.company_name && (
                      <span className="text-xs text-gray-500 truncate">{instr.company_name}</span>
                    )}
                  </span>
                  <span className="text-[10px] text-gray-600 shrink-0 ml-2">{instr.exchange}</span>
                </button>
              ))}
              {searching && (
                <div className="px-3 py-1.5 text-[11px] text-gray-600">Mencari…</div>
              )}
            </div>
          )}
        </div>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
        >
          {loading ? "Memuat..." : "Cari"}
        </button>
      </form>

      {/* Quick picks */}
      <div className="flex flex-wrap gap-2">
        {["BBCA", "BBRI", "BMRI", "TLKM", "AAPL", "MSFT", "NVDA"].map((sym) => (
          <button
            key={sym}
            onClick={() => {
              setQuery(sym);
              searchTicker(sym);
            }}
            className="px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-xs text-gray-400 hover:text-gray-200 rounded transition-colors border border-gray-700"
          >
            {sym}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3">
          <p className="text-sm text-red-400">{error}</p>
          <p className="text-xs text-gray-500 mt-1">
            Pastikan backend berjalan dan ticker ada di database (jalankan bootstrap terlebih dahulu).
          </p>
        </div>
      )}

      {/* Results */}
      {overview && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            {freshness && <FreshnessChip freshness={freshness} />}
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="inline-flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-lg border border-gray-700/60 bg-gray-800/50 text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              title="Re-ingest data via fallback chain"
            >
              <RefreshCw size={11} className={refreshing ? "animate-spin" : ""} />
              {refreshing ? "Menyegarkan…" : "Refresh Data"}
            </button>
            <a
              href={api.stocks.exportCsvUrl(overview.instrument.canonical_symbol)}
              download
              className="inline-flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-lg border border-gray-700/60 bg-gray-800/50 text-gray-400 hover:text-gray-200 hover:border-gray-600 transition-colors"
              title="Unduh OHLCV sebagai CSV"
            >
              <Download size={11} />
              Export CSV
            </a>
          </div>

          {refreshResult && (
            <div className={`text-[11px] px-3 py-2 rounded-lg border ${
              refreshResult.status === "ok"
                ? "bg-emerald-900/15 border-emerald-800/40 text-emerald-400"
                : "bg-amber-900/15 border-amber-800/40 text-amber-400"
            }`}>
              {refreshResult.status === "ok" ? (
                <span>
                  +{refreshResult.bars_added} bar via <strong>{refreshResult.provider_used}</strong>
                  {refreshResult.fallback_used && " (fallback)"}
                  {refreshResult.gap_pct_before !== null && refreshResult.gap_pct_after !== null && refreshResult.gap_pct_before > refreshResult.gap_pct_after && (
                    <span className="ml-1.5 opacity-70">· gap {refreshResult.gap_pct_before}% → {refreshResult.gap_pct_after}%</span>
                  )}
                </span>
              ) : (
                <span>{refreshResult.message ?? "Tidak ada data baru dari provider."}</span>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <StockOverviewCard overview={overview} />
            {recommendation && <RecommendationCard recommendation={recommendation} />}
            {overview.technical && <TechnicalCard technical={overview.technical} />}
            {overview.fundamental && <FundamentalCard fundamental={overview.fundamental} />}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!overview && !loading && !error && (
        <div className="text-center py-20 text-gray-600">
          <Search size={32} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">Masukkan ticker untuk melihat analisis</p>
          <p className="text-xs mt-1">Contoh: BBCA, BMRI.JK, AAPL</p>
        </div>
      )}
    </div>
  );
}
