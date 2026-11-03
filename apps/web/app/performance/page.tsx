"use client";

import React, { useEffect, useState } from "react";
import { api, type PortfolioPerformance, type EquityDataPoint } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { TrendingUp, TrendingDown } from "lucide-react";

const RANGES = ["1m", "3m", "6m", "1y", "2y"] as const;

function MiniLineChart({ points }: { points: EquityDataPoint[] }) {
  if (points.length < 2) return <div className="h-32 flex items-center justify-center text-xs text-gray-600">Data tidak cukup</div>;

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

  // Area fill path
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
      {isPos ? "+" : ""}{pct.toFixed(2)}%
    </span>
  );
}

export default function PerformancePage() {
  const [data, setData] = useState<PortfolioPerformance | null>(null);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<typeof RANGES[number]>("6m");
  const [error, setError] = useState<string | null>(null);

  async function load(r: typeof RANGES[number]) {
    setLoading(true);
    setError(null);
    try {
      const res = await api.performance.get(r);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat performa");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(range); }, [range]);

  const isUp = (data?.total_return_pct ?? 0) >= 0;

  return (
    <div className="p-6 space-y-5 max-w-3xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Performa Portofolio</h1>
        <p className="text-xs text-gray-500 mt-0.5">Equity curve berdasarkan trade history & harga historis</p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">{error}</div>
      )}

      {/* Range selector */}
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

      {loading ? (
        <div className="space-y-3">
          <div className="h-32 bg-gray-800 rounded-xl animate-pulse" />
          <div className="grid grid-cols-3 gap-3">
            {[1,2,3].map(i => <div key={i} className="h-16 bg-gray-800 rounded-lg animate-pulse" />)}
          </div>
        </div>
      ) : data ? (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-gray-500">Total Return</p>
              <p className={`text-xl font-bold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                {isUp ? "+" : ""}{data.total_return_pct.toFixed(2)}%
              </p>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-gray-500">Nilai Saat Ini</p>
              <p className="text-lg font-bold text-gray-100">{formatCurrency(data.current_value)}</p>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-gray-500">Total Invested</p>
              <p className="text-lg font-bold text-gray-300">{formatCurrency(data.total_invested)}</p>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-gray-500">Unrealized P/L</p>
              <p className={`text-lg font-bold ${data.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {data.unrealized_pnl >= 0 ? "+" : ""}{formatCurrency(data.unrealized_pnl)}
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

          {/* Best / Worst */}
          {(data.best_position || data.worst_position) && (
            <div className="grid grid-cols-2 gap-3">
              {data.best_position && (
                <div className="bg-emerald-900/10 border border-emerald-800/30 rounded-lg p-3">
                  <p className="text-xs text-gray-500 flex items-center gap-1 mb-1">
                    <TrendingUp size={11} className="text-emerald-400" /> Terbaik
                  </p>
                  <p className="text-sm font-semibold text-gray-100">
                    {data.best_position.canonical_symbol.split(":")[1] ?? data.best_position.canonical_symbol}
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
                    {data.worst_position.canonical_symbol.split(":")[1] ?? data.worst_position.canonical_symbol}
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
                      <tr key={c.canonical_symbol} className="border-b border-gray-800/50 hover:bg-gray-800/20">
                        <td className="py-2 pr-3 font-medium text-gray-100">{ticker}</td>
                        <td className="py-2 pr-3 text-right text-gray-400">{c.portfolio_weight.toFixed(1)}%</td>
                        <td className="py-2 pr-3 text-right text-gray-400">{formatCurrency(c.total_cost)}</td>
                        <td className="py-2 pr-3 text-right text-gray-300">{formatCurrency(c.current_value)}</td>
                        <td className="py-2 text-right"><PnlBadge pct={c.unrealized_pnl_pct} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {data.equity_curve.length === 0 && data.position_contributions.length === 0 && (
            <div className="text-center py-8 text-gray-600">
              <p className="text-sm">Belum ada data performa — tambahkan transaksi terlebih dahulu</p>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
