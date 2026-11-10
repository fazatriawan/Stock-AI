"use client";

import React, { useEffect, useState } from "react";
import {
  api,
  type PortfolioPerformance,
  type EquityDataPoint,
  type PortfolioAttribution,
} from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { TrendingUp, TrendingDown, Scale } from "lucide-react";

const RANGES = ["1m", "3m", "6m", "1y", "2y"] as const;

function MiniLineChart({ points }: { points: EquityDataPoint[] }) {
  if (points.length < 2)
    return (
      <div className="h-32 flex items-center justify-center text-xs text-gray-600">
        Data tidak cukup
      </div>
    );

  const values = points.map(p => p.portfolio_value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const W = 600;
  const H = 120;
  const pad = 8;

  const coords = points.map((p, i) => {
    const x = pad + (i / (points.length - 1)) * (W - pad * 2);
    const y = H - pad - ((p.portfolio_value - min) / range) * (H - pad * 2);
    return `${x},${y}`;
  });

  const firstVal = points[0].portfolio_value;
  const lastVal = points[points.length - 1].portfolio_value;
  const isUp = lastVal >= firstVal;
  const lineColor = isUp ? "#34d399" : "#f87171";

  const areaPath = `M ${coords[0]} L ${coords.join(" L ")} L ${pad + (W - pad * 2)},${H - pad} L ${pad},${H - pad} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-32" preserveAspectRatio="none">
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity="0.25" />
          <stop offset="100%" stopColor={lineColor} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#areaGrad)" />
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke={lineColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PnlBadge({ pct }: { pct: number }) {
  const isPos = pct >= 0;
  return (
    <span className={`text-xs font-medium ${isPos ? "text-emerald-400" : "text-red-400"}`}>
      {isPos ? "+" : ""}
      {pct.toFixed(2)}%
    </span>
  );
}

export default function PerformancePage() {
  const [data, setData] = useState<PortfolioPerformance | null>(null);
  const [attribution, setAttribution] = useState<PortfolioAttribution | null>(null);
  const [benchmarkPct, setBenchmarkPct] = useState("5.0");
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<(typeof RANGES)[number]>("6m");
  const [error, setError] = useState<string | null>(null);

  async function load(r: (typeof RANGES)[number], bmPct: number) {
    setLoading(true);
    setError(null);
    try {
      const [perfRes, attrRes] = await Promise.all([
        api.performance.get(r),
        api.performance.attribution(bmPct),
      ]);
      setData(perfRes);
      setAttribution(attrRes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat performa");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const bm = parseFloat(benchmarkPct);
    load(range, Number.isFinite(bm) ? bm : 5.0);
  }, [range]);

  const isUp = (data?.total_return_pct ?? 0) >= 0;

  return (
    <div className="p-6 space-y-5 max-w-4xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">
          Performa & Atribusi Keputusan (HARD-05)
        </h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Equity curve dan dekomposisi return terhadap benchmark, sektor, dividen, & biaya transaksi
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Range selector */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1.5">
          {RANGES.map(r => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1 rounded text-xs transition-colors ${
                range === r ? "bg-gray-700 text-gray-100" : "text-gray-500 hover:text-gray-300"
              }`}
            >
              {r}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="text-gray-500">Return Acuan (IHSG %):</span>
          <input
            type="number"
            step="0.5"
            value={benchmarkPct}
            onChange={e => setBenchmarkPct(e.target.value)}
            className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
          />
          <button
            onClick={() => {
              const bm = parseFloat(benchmarkPct);
              load(range, Number.isFinite(bm) ? bm : 0.0);
            }}
            className="px-2.5 py-1 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-xs"
          >
            Hitung Atribusi
          </button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          <div className="h-32 bg-gray-800 rounded-xl animate-pulse" />
          <div className="grid grid-cols-3 gap-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 bg-gray-800 rounded-lg animate-pulse" />
            ))}
          </div>
        </div>
      ) : data ? (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-gray-500">Total Return</p>
              <p className={`text-xl font-bold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                {isUp ? "+" : ""}
                {data.total_return_pct.toFixed(2)}%
              </p>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-gray-500">Nilai Saat Ini</p>
              <p className="text-lg font-bold text-gray-100">
                {formatCurrency(data.current_value)}
              </p>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-gray-500">Total Invested</p>
              <p className="text-lg font-bold text-gray-300">
                {formatCurrency(data.total_invested)}
              </p>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-gray-500">Unrealized P/L</p>
              <p
                className={`text-lg font-bold ${
                  data.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {data.unrealized_pnl >= 0 ? "+" : ""}
                {formatCurrency(data.unrealized_pnl)}
              </p>
            </div>
          </div>

          {/* Equity curve */}
          <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4">
            <p className="text-xs text-gray-500 mb-3">Nilai Portofolio</p>
            {data.equity_curve.length >= 2 ? (
              <MiniLineChart points={data.equity_curve} />
            ) : (
              <div className="h-32 flex items-center justify-center text-xs text-gray-600">
                Data harga tidak cukup untuk menampilkan grafik
              </div>
            )}
            {data.equity_curve.length >= 2 && (
              <div className="flex justify-between text-xs text-gray-600 mt-1">
                <span>{data.equity_curve[0]?.date}</span>
                <span>{data.equity_curve[data.equity_curve.length - 1]?.date}</span>
              </div>
            )}
          </div>

          {/* HARD-05 Decision Attribution Panel */}
          {attribution && (
            <div className="bg-gray-800/30 border border-blue-900/40 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-blue-400 flex items-center gap-1.5">
                  <Scale size={13} /> HARD-05 — Decision & Return Attribution (vs Benchmark{" "}
                  {attribution.benchmark_return_pct.toFixed(1)}%)
                </p>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 text-xs">
                <div className="bg-gray-900/50 rounded-lg p-2.5">
                  <p className="text-gray-500">Excess vs Benchmark</p>
                  <PnlBadge pct={attribution.portfolio_excess_return_pct} />
                </div>
                <div className="bg-gray-900/50 rounded-lg p-2.5">
                  <p className="text-gray-500">Stock-Specific Alpha</p>
                  <PnlBadge pct={attribution.weighted_stock_alpha_pct} />
                </div>
                <div className="bg-gray-900/50 rounded-lg p-2.5">
                  <p className="text-gray-500">Kontribusi Dividen</p>
                  <PnlBadge pct={attribution.weighted_dividend_pct} />
                </div>
                <div className="bg-gray-900/50 rounded-lg p-2.5">
                  <p className="text-gray-500">Beban Biaya (Cost Drag)</p>
                  <PnlBadge pct={attribution.weighted_cost_drag_pct} />
                </div>
              </div>

              {attribution.positions.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-gray-500 border-b border-gray-800">
                        <th className="text-left py-1.5 pr-3">Ticker</th>
                        <th className="text-right py-1.5 pr-3">Bobot</th>
                        <th className="text-right py-1.5 pr-3">Return Net</th>
                        <th className="text-right py-1.5 pr-3">Stock Alpha</th>
                        <th className="text-right py-1.5 pr-3">Dividen</th>
                        <th className="text-right py-1.5 pr-3">Cost Drag</th>
                        <th className="text-right py-1.5">Excess vs Acuan</th>
                      </tr>
                    </thead>
                    <tbody>
                      {attribution.positions.map(p => (
                        <tr key={p.symbol} className="border-b border-gray-800/40">
                          <td className="py-1.5 pr-3 font-medium text-gray-200">{p.symbol}</td>
                          <td className="py-1.5 pr-3 text-right text-gray-400">
                            {(p.weight * 100).toFixed(1)}%
                          </td>
                          <td className="py-1.5 pr-3 text-right">
                            <PnlBadge pct={p.total_return_pct} />
                          </td>
                          <td className="py-1.5 pr-3 text-right">
                            <PnlBadge pct={p.stock_specific_alpha_pct} />
                          </td>
                          <td className="py-1.5 pr-3 text-right text-gray-300">
                            +{p.dividend_contribution_pct.toFixed(2)}%
                          </td>
                          <td className="py-1.5 pr-3 text-right text-amber-400">
                            {p.cost_drag_pct.toFixed(2)}%
                          </td>
                          <td className="py-1.5 text-right">
                            <PnlBadge pct={p.baseline_excess_pct} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <p className="text-[11px] text-gray-500 italic">{attribution.caveat}</p>
            </div>
          )}

          {/* Best / Worst */}
          {(data.best_position || data.worst_position) && (
            <div className="grid grid-cols-2 gap-3">
              {data.best_position && (
                <div className="bg-emerald-900/10 border border-emerald-800/30 rounded-lg p-3">
                  <p className="text-xs text-gray-500 flex items-center gap-1 mb-1">
                    <TrendingUp size={11} className="text-emerald-400" /> Terbaik
                  </p>
                  <p className="text-sm font-semibold text-gray-100">
                    {data.best_position.canonical_symbol.split(":")[1] ??
                      data.best_position.canonical_symbol}
                  </p>
                  <PnlBadge pct={data.best_position.unrealized_pnl_pct} />
                </div>
              )}
              {data.worst_position && (
                <div className="bg-red-900/10 border border-red-800/30 rounded-lg p-3">
                  <p className="text-xs text-gray-500 flex items-center gap-1 mb-1">
                    <TrendingDown size={11} className="text-red-400" /> Terburuk
                  </p>
                  <p className="text-sm font-semibold text-gray-100">
                    {data.worst_position.canonical_symbol.split(":")[1] ??
                      data.worst_position.canonical_symbol}
                  </p>
                  <PnlBadge pct={data.worst_position.unrealized_pnl_pct} />
                </div>
              )}
            </div>
          )}

          {/* Position contribution table */}
          {data.position_contributions.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-gray-500">Kontribusi per Posisi</p>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-800">
                    <th className="text-left py-2 pr-3">Ticker</th>
                    <th className="text-right py-2 pr-3">Bobot</th>
                    <th className="text-right py-2 pr-3">Modal</th>
                    <th className="text-right py-2 pr-3">Nilai</th>
                    <th className="text-right py-2">Return</th>
                  </tr>
                </thead>
                <tbody>
                  {data.position_contributions.map(c => {
                    const ticker = c.canonical_symbol.split(":")[1] ?? c.canonical_symbol;
                    return (
                      <tr
                        key={c.canonical_symbol}
                        className="border-b border-gray-800/50 hover:bg-gray-800/20"
                      >
                        <td className="py-2 pr-3 font-medium text-gray-100">{ticker}</td>
                        <td className="py-2 pr-3 text-right text-gray-400">
                          {c.portfolio_weight.toFixed(1)}%
                        </td>
                        <td className="py-2 pr-3 text-right text-gray-400">
                          {formatCurrency(c.total_cost)}
                        </td>
                        <td className="py-2 pr-3 text-right text-gray-300">
                          {formatCurrency(c.current_value)}
                        </td>
                        <td className="py-2 text-right">
                          <PnlBadge pct={c.unrealized_pnl_pct} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {data.equity_curve.length === 0 && data.position_contributions.length === 0 && (
            <div className="text-center py-8 text-gray-600">
              <p className="text-sm">
                Belum ada data performa — tambahkan transaksi terlebih dahulu
              </p>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
