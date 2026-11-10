"use client";

import React, { useState } from "react";
import {
  api,
  type ScreenerResult,
  type ScreenerFilters,
  type MultibaggerResult,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Search, SlidersHorizontal, Sparkles, ChevronDown, ChevronUp } from "lucide-react";

const ACTION_VARIANT: Record<string, "success" | "danger" | "warning" | "default"> = {
  BUY: "success",
  ADD_CANDIDATE: "success",
  HOLD: "default",
  WAIT: "default",
  TRIM_CANDIDATE: "warning",
  SELL: "danger",
  INSUFFICIENT_DATA: "default",
};

const TIER_VARIANT: Record<string, "success" | "warning" | "default" | "danger"> = {
  STRONG: "success",
  MODERATE: "warning",
  WEAK: "default",
  NOT_QUALIFIED: "danger",
  INSUFFICIENT: "default",
};

const PIPELINE_LABELS: Record<string, string> = {
  QUALITY_COMPOUNDER: "Quality Compounder",
  EARNINGS_INFLECTION: "Earnings Inflection",
  TURNAROUND: "Turnaround",
  UNDERAPPRECIATED_CATALYST: "Underappreciated Catalyst",
};

const SECTORS = [
  "Finance",
  "Financials",
  "Consumer",
  "Telecoms",
  "Energy",
  "Materials",
  "Healthcare",
  "Industrial",
  "Technology",
  "Property",
];
const EXCHANGES = ["IDX", "NASDAQ", "NYSE"];

function FreshnessChip({ freshness }: { freshness: string }) {
  const color =
    freshness === "FRESH"
      ? "text-emerald-400"
      : freshness === "ACCEPTABLE"
        ? "text-amber-400"
        : "text-gray-500";
  return <span className={`text-xs ${color}`}>{freshness}</span>;
}

function ScorePill({ score }: { score: number }) {
  const bg =
    score >= 60
      ? "bg-emerald-900/30 text-emerald-300"
      : score >= 45
        ? "bg-amber-900/30 text-amber-300"
        : "bg-gray-800 text-gray-400";
  return <span className={`text-xs px-1.5 py-0.5 rounded ${bg}`}>{score.toFixed(0)}</span>;
}

export default function ScreenerPage() {
  const [activeTab, setActiveTab] = useState<"standard" | "multibagger">("standard");

  // Standard Screener state
  const [results, setResults] = useState<ScreenerResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  // Filter state
  const [sector, setSector] = useState("");
  const [exchange, setExchange] = useState("");
  const [minRoe, setMinRoe] = useState("");
  const [maxPe, setMaxPe] = useState("");
  const [minPe, setMinPe] = useState("");
  const [minScore, setMinScore] = useState("");
  const [action, setAction] = useState("");

  // Multibagger Lab state
  const [mbResults, setMbResults] = useState<MultibaggerResult[]>([]);
  const [mbLoading, setMbLoading] = useState(false);
  const [mbError, setMbError] = useState<string | null>(null);
  const [mbSearched, setMbSearched] = useState(false);
  const [mbMinTier, setMbMinTier] = useState("WEAK");
  const [mbPipelineFilter, setMbPipelineFilter] = useState("");
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);

  async function runScreen() {
    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const filters: ScreenerFilters = { limit: 100 };
      if (sector) filters.sector = sector;
      if (exchange) filters.exchange = exchange;
      if (minRoe) filters.min_roe = parseFloat(minRoe) / 100;
      if (maxPe) filters.max_pe = parseFloat(maxPe);
      if (minPe) filters.min_pe = parseFloat(minPe);
      if (minScore) filters.min_composite = parseFloat(minScore);
      if (action) filters.action = action;
      const res = await api.screener.screen(filters);
      setResults(res.results);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Screener gagal");
    } finally {
      setLoading(false);
    }
  }

  async function runMultibaggerScreen() {
    setMbLoading(true);
    setMbError(null);
    setMbSearched(true);
    try {
      const res = await api.screener.multibagger({
        sector: sector || undefined,
        exchange: exchange || undefined,
        min_tier: mbMinTier,
        limit: 100,
      });
      setMbResults(res.results);
    } catch (e) {
      setMbError(e instanceof Error ? e.message : "Multibagger screener gagal");
    } finally {
      setMbLoading(false);
    }
  }

  function reset() {
    setSector("");
    setExchange("");
    setMinRoe("");
    setMaxPe("");
    setMinPe("");
    setMinScore("");
    setAction("");
    setResults([]);
    setHasSearched(false);
    setMbResults([]);
    setMbSearched(false);
    setMbPipelineFilter("");
  }

  const filteredMbResults = mbPipelineFilter
    ? mbResults.filter(r => r.score.pipelines_matched?.includes(mbPipelineFilter))
    : mbResults;

  return (
    <div className="p-6 space-y-5">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Screener & Multibagger Lab</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Saring kandidat riset saham berdasarkan fundamental, teknikal, & 4 pipeline Multibagger (PRD v1.7.1)
          </p>
        </div>

        {/* Tab switcher */}
        <div className="inline-flex rounded-lg bg-gray-800/70 p-1 border border-gray-700/60 self-start">
          <button
            onClick={() => setActiveTab("standard")}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === "standard"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Screener Umum
          </button>
          <button
            onClick={() => setActiveTab("multibagger")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === "multibagger"
                ? "bg-emerald-600 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            <Sparkles size={12} />
            Multibagger Lab (4 Pipeline)
          </button>
        </div>
      </div>

      {activeTab === "standard" ? (
        <>
          {/* Filter panel */}
          <div className="bg-gray-800/40 border border-gray-700/50 rounded-xl p-4 space-y-4">
            <div className="flex items-center gap-2 text-xs text-gray-400 font-medium">
              <SlidersHorizontal size={13} /> Filter Fundamental & Teknikal
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Sektor</label>
                <select
                  value={sector}
                  onChange={e => setSector(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                >
                  <option value="">Semua</option>
                  {SECTORS.map(s => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Bursa</label>
                <select
                  value={exchange}
                  onChange={e => setExchange(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                >
                  <option value="">Semua</option>
                  {EXCHANGES.map(x => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">ROE min (%)</label>
                <input
                  type="number"
                  value={minRoe}
                  onChange={e => setMinRoe(e.target.value)}
                  placeholder="cth: 10"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">P/E maks</label>
                <input
                  type="number"
                  value={maxPe}
                  onChange={e => setMaxPe(e.target.value)}
                  placeholder="cth: 20"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">P/E min</label>
                <input
                  type="number"
                  value={minPe}
                  onChange={e => setMinPe(e.target.value)}
                  placeholder="cth: 3"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Skor komposit min</label>
                <input
                  type="number"
                  value={minScore}
                  onChange={e => setMinScore(e.target.value)}
                  placeholder="cth: 50"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Sinyal engine</label>
                <select
                  value={action}
                  onChange={e => setAction(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                >
                  <option value="">Semua</option>
                  {["BUY", "WAIT", "HOLD", "TRIM_CANDIDATE", "SELL"].map(a => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex gap-2 pt-1">
              <button
                onClick={runScreen}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
              >
                <Search size={12} />
                {loading ? "Memuat..." : "Jalankan Screener"}
              </button>
              <button
                onClick={reset}
                className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Reset
              </button>
            </div>
          </div>

          {error && (
            <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {/* Results table */}
          {results.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-gray-500">{results.length} saham ditemukan</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b border-gray-800">
                      <th className="text-left py-2 pr-3">Ticker</th>
                      <th className="text-left py-2 pr-3">Sektor</th>
                      <th className="text-right py-2 pr-3">Harga</th>
                      <th className="text-right py-2 pr-3">PE</th>
                      <th className="text-right py-2 pr-3">ROE%</th>
                      <th className="text-right py-2 pr-3">RSI</th>
                      <th className="text-center py-2 pr-3">SMA200</th>
                      <th className="text-right py-2 pr-3">Skor</th>
                      <th className="text-center py-2 pr-3">Sinyal</th>
                      <th className="text-center py-2">Data</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map(r => {
                      const ticker = r.canonical_symbol.split(":")[1] ?? r.canonical_symbol;
                      return (
                        <tr
                          key={r.instrument_id}
                          className="border-b border-gray-800/50 hover:bg-gray-800/30"
                        >
                          <td className="py-2 pr-3">
                            <span className="font-medium text-gray-100">{ticker}</span>
                            {r.company_name && (
                              <p className="text-gray-600 truncate max-w-[120px]">
                                {r.company_name}
                              </p>
                            )}
                          </td>
                          <td className="py-2 pr-3 text-gray-400">{r.sector ?? "—"}</td>
                          <td className="py-2 pr-3 text-right text-gray-300">
                            {r.current_price != null
                              ? `Rp ${r.current_price.toLocaleString("id-ID")}`
                              : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right text-gray-300">
                            {r.pe_ratio != null ? r.pe_ratio.toFixed(1) : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right text-gray-300">
                            {r.roe != null ? (r.roe * 100).toFixed(1) : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right text-gray-300">
                            {r.rsi_14 != null ? r.rsi_14.toFixed(0) : "—"}
                          </td>
                          <td className="py-2 pr-3 text-center">
                            {r.above_sma_200 == null ? (
                              "—"
                            ) : r.above_sma_200 ? (
                              <span className="text-emerald-400">↑</span>
                            ) : (
                              <span className="text-red-400">↓</span>
                            )}
                          </td>
                          <td className="py-2 pr-3 text-right">
                            <ScorePill score={r.composite_score} />
                          </td>
                          <td className="py-2 pr-3 text-center">
                            <Badge variant={ACTION_VARIANT[r.action]}>{r.action}</Badge>
                          </td>
                          <td className="py-2 text-center">
                            <FreshnessChip freshness={r.data_freshness} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {hasSearched && !loading && results.length === 0 && !error && (
            <div className="text-center py-12 text-gray-600 space-y-2">
              <Search size={28} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">Tidak ada saham yang cocok dengan filter ini</p>
              <p className="text-xs text-gray-700 max-w-sm mx-auto">
                Screener memerlukan data fundamental lengkap (revenue growth, EPS, ROE, dll). Jika
                hasil selalu 0, jalankan{" "}
                <strong className="text-gray-500">refresh fundamentals</strong> di halaman{" "}
                <a href="/settings" className="text-blue-500 hover:underline">
                  Settings
                </a>{" "}
                terlebih dahulu.
              </p>
            </div>
          )}

          {!hasSearched && (
            <div className="text-center py-16 text-gray-600">
              <SlidersHorizontal size={28} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">Atur filter di atas, lalu klik Jalankan Screener</p>
            </div>
          )}
        </>
      ) : (
        /* Multibagger Research Lab Tab */
        <div className="space-y-4">
          <div className="bg-gray-800/40 border border-emerald-800/30 rounded-xl p-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs text-emerald-400 font-medium">
                <Sparkles size={13} /> MULTI-01 & MULTI-02 — 4 Pipeline Riset & Reverse Scenario
              </div>
              <span className="text-[11px] text-gray-500">
                Output adalah kandidat riset, bukan sinyal beli otomatis
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Bursa</label>
                <select
                  value={exchange}
                  onChange={e => setExchange(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                >
                  <option value="">Semua</option>
                  {EXCHANGES.map(x => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Sektor</label>
                <select
                  value={sector}
                  onChange={e => setSector(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                >
                  <option value="">Semua</option>
                  {SECTORS.map(s => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Tier Minimum</label>
                <select
                  value={mbMinTier}
                  onChange={e => setMbMinTier(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                >
                  <option value="STRONG">STRONG (≥70)</option>
                  <option value="MODERATE">MODERATE (≥50)</option>
                  <option value="WEAK">WEAK (≥30)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Filter Pipeline (MULTI-01)</label>
                <select
                  value={mbPipelineFilter}
                  onChange={e => setMbPipelineFilter(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                >
                  <option value="">Semua Pipeline</option>
                  {Object.entries(PIPELINE_LABELS).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex gap-2 pt-1">
              <button
                onClick={runMultibaggerScreen}
                disabled={mbLoading}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
              >
                <Sparkles size={12} />
                {mbLoading ? "Memindai Kandidat..." : "Cari Kandidat Multibagger"}
              </button>
              <button
                onClick={reset}
                className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Reset
              </button>
            </div>
          </div>

          {mbError && (
            <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">
              {mbError}
            </div>
          )}

          {filteredMbResults.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs text-gray-500">
                {filteredMbResults.length} kandidat riset ditemukan
              </p>

              {filteredMbResults.map(item => {
                const isExpanded = expandedSymbol === item.canonical_symbol;
                const pipelines = item.score.pipelines_matched ?? [];
                const scenarios = item.score.reverse_scenarios ?? [];

                return (
                  <div
                    key={item.instrument_id}
                    className="bg-gray-800/30 border border-gray-700/50 rounded-xl p-4 space-y-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-gray-100">
                            {item.canonical_symbol}
                          </span>
                          <Badge variant={TIER_VARIANT[item.score.tier] ?? "default"}>
                            {item.score.tier} ({item.score.total_score.toFixed(0)}/100)
                          </Badge>
                          <span className="text-xs text-gray-500">{item.sector ?? "—"}</span>
                        </div>
                        {item.company_name && (
                          <p className="text-xs text-gray-400 mt-0.5">{item.company_name}</p>
                        )}
                      </div>

                      <div className="text-right text-xs">
                        <p className="text-gray-200 font-medium">
                          {item.current_price != null
                            ? `Rp ${item.current_price.toLocaleString("id-ID")}`
                            : "Harga N/A"}
                        </p>
                        <p className="text-gray-500">
                          PE: {item.pe_ratio != null ? `${item.pe_ratio.toFixed(1)}x` : "—"} · ROE:{" "}
                          {item.roe != null ? `${item.roe.toFixed(1)}%` : "—"} · Data:{" "}
                          {(item.score.data_completeness * 100).toFixed(0)}%
                        </p>
                      </div>
                    </div>

                    {/* Matched Pipelines Badges */}
                    <div className="flex flex-wrap gap-1.5">
                      {pipelines.length > 0 ? (
                        pipelines.map(p => (
                          <span
                            key={p}
                            className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-950/60 border border-emerald-700/40 text-emerald-300"
                          >
                            {PIPELINE_LABELS[p] ?? p}
                          </span>
                        ))
                      ) : (
                        <span className="text-[11px] text-gray-500">
                          Belum memenuhi threshold pipeline spesifik
                        </span>
                      )}
                    </div>

                    {/* Strengths & Concerns */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                      <div className="bg-emerald-950/20 border border-emerald-900/30 rounded-lg p-2.5">
                        <p className="text-emerald-400 font-medium mb-1">Faktor Pendukung</p>
                        {item.score.strengths.length > 0 ? (
                          <ul className="list-disc list-inside text-gray-300 space-y-0.5">
                            {item.score.strengths.map((s, idx) => (
                              <li key={idx}>{s}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-gray-500">Tidak ada highlight spesifik</p>
                        )}
                      </div>

                      <div className="bg-amber-950/20 border border-amber-900/30 rounded-lg p-2.5">
                        <p className="text-amber-400 font-medium mb-1">Risiko & Kontra-Argumen</p>
                        {item.score.concerns.length > 0 ? (
                          <ul className="list-disc list-inside text-gray-300 space-y-0.5">
                            {item.score.concerns.map((c, idx) => (
                              <li key={idx}>{c}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-gray-500">Periksa laporan keuangan & likuiditas</p>
                        )}
                      </div>
                    </div>

                    {/* Reverse Multibagger Scenario Toggle */}
                    {scenarios.length > 0 && (
                      <div>
                        <button
                          onClick={() =>
                            setExpandedSymbol(isExpanded ? null : item.canonical_symbol)
                          }
                          className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
                        >
                          {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                          Reverse Multibagger Scenario (Syarat EPS CAGR 2x–10x dalam 5 Tahun)
                        </button>

                        {isExpanded && (
                          <div className="mt-2 bg-gray-900/60 border border-gray-800 rounded-lg p-3 overflow-x-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="text-gray-500 border-b border-gray-800">
                                  <th className="text-left py-1.5 pr-3">Target</th>
                                  <th className="text-right py-1.5 pr-3">Horizon</th>
                                  <th className="text-right py-1.5 pr-3">
                                    Syarat EPS CAGR (PE Tetap)
                                  </th>
                                  <th className="text-right py-1.5 pr-3">
                                    Syarat EPS CAGR (Re-rating)
                                  </th>
                                  <th className="text-right py-1.5 pr-3">Asumsi Dilusi/Thn</th>
                                  <th className="text-left py-1.5">Catatan Risiko (Anti-Hype)</th>
                                </tr>
                              </thead>
                              <tbody>
                                {scenarios.map(sc => (
                                  <tr
                                    key={sc.target_multiple}
                                    className="border-b border-gray-800/40"
                                  >
                                    <td className="py-1.5 pr-3 font-semibold text-emerald-400">
                                      {sc.target_multiple}x
                                    </td>
                                    <td className="py-1.5 pr-3 text-right text-gray-400">
                                      {sc.horizon_years} thn
                                    </td>
                                    <td className="py-1.5 pr-3 text-right text-gray-200">
                                      {sc.required_eps_cagr_constant_pe_pct.toFixed(1)}%/thn
                                    </td>
                                    <td className="py-1.5 pr-3 text-right text-gray-300">
                                      {sc.required_eps_cagr_rerating_pct != null
                                        ? `${sc.required_eps_cagr_rerating_pct.toFixed(1)}%/thn`
                                        : "—"}
                                    </td>
                                    <td className="py-1.5 pr-3 text-right text-gray-400">
                                      {sc.assumed_annual_dilution_pct.toFixed(1)}%
                                    </td>
                                    <td className="py-1.5 text-gray-400">
                                      {sc.downside_risk_note}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {mbSearched && !mbLoading && filteredMbResults.length === 0 && !mbError && (
            <div className="text-center py-12 text-gray-600 space-y-2">
              <Sparkles size={28} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">Belum ada kandidat yang lolos filter Multibagger ini</p>
              <p className="text-xs text-gray-700 max-w-sm mx-auto">
                Coba turunkan Tier Minimum ke WEAK atau pilih Semua Pipeline.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
