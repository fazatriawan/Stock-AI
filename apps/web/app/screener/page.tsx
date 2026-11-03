"use client";

import React, { useState } from "react";
import { api, type ScreenerResult, type ScreenerFilters } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Search, SlidersHorizontal } from "lucide-react";

const ACTION_VARIANT: Record<string, "success" | "danger" | "warning" | "default"> = {
  BUY: "success", ADD_CANDIDATE: "success",
  HOLD: "default", WAIT: "default",
  TRIM_CANDIDATE: "warning", SELL: "danger",
  INSUFFICIENT_DATA: "default",
};

const SECTORS = ["Finance", "Consumer", "Telecoms", "Energy", "Materials", "Healthcare", "Industrial", "Technology", "Property"];
const EXCHANGES = ["IDX", "NASDAQ", "NYSE"];

function FreshnessChip({ freshness }: { freshness: string }) {
  const color = freshness === "FRESH" ? "text-emerald-400" : freshness === "ACCEPTABLE" ? "text-amber-400" : "text-gray-500";
  return <span className={`text-xs ${color}`}>{freshness}</span>;
}

function ScorePill({ score }: { score: number }) {
  const bg = score >= 60 ? "bg-emerald-900/30 text-emerald-300" : score >= 45 ? "bg-amber-900/30 text-amber-300" : "bg-gray-800 text-gray-400";
  return <span className={`text-xs px-1.5 py-0.5 rounded ${bg}`}>{score.toFixed(0)}</span>;
}

export default function ScreenerPage() {
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

  function reset() {
    setSector(""); setExchange(""); setMinRoe(""); setMaxPe("");
    setMinPe(""); setMinScore(""); setAction("");
    setResults([]); setHasSearched(false);
  }

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Screener</h1>
        <p className="text-xs text-gray-500 mt-0.5">Filter saham berdasarkan kriteria fundamental & teknikal</p>
      </div>

      {/* Filter panel */}
      <div className="bg-gray-800/40 border border-gray-700/50 rounded-xl p-4 space-y-4">
        <div className="flex items-center gap-2 text-xs text-gray-400 font-medium">
          <SlidersHorizontal size={13} /> Filter
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
              {SECTORS.map(s => <option key={s} value={s}>{s}</option>)}
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
              {EXCHANGES.map(x => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">ROE min (%)</label>
            <input
              type="number" value={minRoe} onChange={e => setMinRoe(e.target.value)}
              placeholder="cth: 10"
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
            />
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">P/E maks</label>
            <input
              type="number" value={maxPe} onChange={e => setMaxPe(e.target.value)}
              placeholder="cth: 20"
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
            />
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">P/E min</label>
            <input
              type="number" value={minPe} onChange={e => setMinPe(e.target.value)}
              placeholder="cth: 3"
              className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
            />
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Skor komposit min</label>
            <input
              type="number" value={minScore} onChange={e => setMinScore(e.target.value)}
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
                <option key={a} value={a}>{a}</option>
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
                    <tr key={r.instrument_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                      <td className="py-2 pr-3">
                        <span className="font-medium text-gray-100">{ticker}</span>
                        {r.company_name && (
                          <p className="text-gray-600 truncate max-w-[120px]">{r.company_name}</p>
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
                        {r.above_sma_200 == null ? "—"
                          : r.above_sma_200
                            ? <span className="text-emerald-400">↑</span>
                            : <span className="text-red-400">↓</span>}
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
        <div className="text-center py-12 text-gray-600">
          <Search size={28} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">Tidak ada saham yang cocok dengan filter ini</p>
        </div>
      )}

      {!hasSearched && (
        <div className="text-center py-16 text-gray-600">
          <SlidersHorizontal size={28} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">Atur filter di atas, lalu klik Jalankan Screener</p>
        </div>
      )}
    </div>
  );
}
