"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type PortfolioSummary, type Position } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TrendingUp, TrendingDown, Minus, ExternalLink, AlertTriangle } from "lucide-react";

type SortKey = "weight" | "pnl_pct" | "total_cost" | "lots";
type SortDir = "asc" | "desc";

const PNL_TIER = (pct: number) => {
  if (pct >= 0.15) return { label: "+15%+", color: "text-emerald-300", bg: "bg-emerald-900/30" };
  if (pct >= 0.05) return { label: "+5~15%", color: "text-emerald-400", bg: "bg-emerald-900/20" };
  if (pct >= -0.05) return { label: "−5~+5%", color: "text-gray-400", bg: "bg-gray-800/30" };
  if (pct >= -0.15) return { label: "−5~15%", color: "text-red-400", bg: "bg-red-900/20" };
  return { label: "−15%↓", color: "text-red-300", bg: "bg-red-900/30" };
};

function PositionRow({ pos, rank }: { pos: Position; rank: number }) {
  const router = useRouter();
  const ticker = pos.canonical_symbol.split(":")[1] ?? pos.canonical_symbol;
  const hasPnl = pos.unrealized_pnl_pct !== null && pos.unrealized_pnl_pct !== undefined;
  const tier = hasPnl ? PNL_TIER(pos.unrealized_pnl_pct!) : null;

  return (
    <tr className="border-b border-gray-800/50 hover:bg-gray-800/20 cursor-pointer" onClick={() => router.push(`/explorer?q=${encodeURIComponent(pos.canonical_symbol)}`)}>
      <td className="py-3 px-4">
        <span className="text-xs text-gray-600">{rank}</span>
      </td>
      <td className="py-3 px-4">
        <div>
          <p className="text-sm font-medium text-gray-100">{ticker}</p>
          {pos.company_name && <p className="text-xs text-gray-600 truncate max-w-[140px]">{pos.company_name}</p>}
        </div>
      </td>
      <td className="py-3 px-4">
        {pos.sector ? (
          <span className="text-xs text-gray-500 bg-gray-800 rounded px-2 py-0.5">{pos.sector}</span>
        ) : (
          <span className="text-xs text-gray-700">—</span>
        )}
      </td>
      <td className="py-3 px-4 text-right">
        <p className="text-sm text-gray-300">{pos.lots}</p>
        <p className="text-xs text-gray-600">{pos.shares.toLocaleString()} lembar</p>
      </td>
      <td className="py-3 px-4 text-right">
        <p className="text-sm text-gray-300">{formatCurrency(pos.avg_cost)}</p>
      </td>
      <td className="py-3 px-4 text-right">
        {pos.current_price ? (
          <p className="text-sm text-gray-300">{formatCurrency(pos.current_price)}</p>
        ) : (
          <p className="text-xs text-gray-700">—</p>
        )}
      </td>
      <td className="py-3 px-4 text-right">
        {hasPnl && tier ? (
          <div className={`inline-flex flex-col items-end rounded px-2 py-1 ${tier.bg}`}>
            <span className={`text-sm font-medium ${tier.color}`}>
              {pos.unrealized_pnl_pct! >= 0 ? "+" : ""}{formatPercent(pos.unrealized_pnl_pct!)}
            </span>
            <span className={`text-xs ${tier.color}`}>{formatCurrency(pos.unrealized_pnl!)}</span>
          </div>
        ) : (
          <span className="text-xs text-gray-700">—</span>
        )}
      </td>
      <td className="py-3 px-4 text-right">
        <div className="flex items-center justify-end gap-2">
          <div className="h-1.5 w-20 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-600 rounded-full"
              style={{ width: `${Math.min(100, pos.weight * 100)}%` }}
            />
          </div>
          <span className="text-xs text-gray-400 w-10 text-right">{(pos.weight * 100).toFixed(1)}%</span>
        </div>
      </td>
      <td className="py-3 px-4 text-center">
        <ExternalLink size={12} className="text-gray-700 inline" />
      </td>
    </tr>
  );
}

export default function PositionIntelligencePage() {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("weight");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [filter, setFilter] = useState<"ALL" | "PROFIT" | "LOSS" | "NO_PRICE">("ALL");

  useEffect(() => {
    api.portfolio.summary()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-6 w-48 bg-gray-800 rounded animate-pulse" />
        <div className="h-64 bg-gray-800 rounded-lg animate-pulse" />
      </div>
    );
  }

  if (error) return <div className="p-6"><p className="text-red-400 text-sm">{error}</p></div>;
  if (!data) return null;

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  }

  const sorted = [...data.positions]
    .filter((p) => {
      if (filter === "PROFIT") return p.unrealized_pnl_pct !== null && p.unrealized_pnl_pct! > 0;
      if (filter === "LOSS") return p.unrealized_pnl_pct !== null && p.unrealized_pnl_pct! < -0.05;
      if (filter === "NO_PRICE") return p.current_price === null;
      return true;
    })
    .sort((a, b) => {
      let av = 0, bv = 0;
      if (sortKey === "weight") { av = a.weight; bv = b.weight; }
      else if (sortKey === "pnl_pct") { av = a.unrealized_pnl_pct ?? -999; bv = b.unrealized_pnl_pct ?? -999; }
      else if (sortKey === "total_cost") { av = a.total_cost; bv = b.total_cost; }
      else if (sortKey === "lots") { av = a.lots; bv = b.lots; }
      return sortDir === "asc" ? av - bv : bv - av;
    });

  const noPriceCount = data.positions.filter(p => p.current_price === null).length;
  const lossCount = data.positions.filter(p => p.unrealized_pnl_pct !== null && p.unrealized_pnl_pct! < -0.05).length;

  function SortTh({ label, k }: { label: string; k: SortKey }) {
    const active = sortKey === k;
    return (
      <th
        className="py-2.5 px-4 text-right cursor-pointer hover:text-gray-300 select-none"
        onClick={() => toggleSort(k)}
      >
        <span className={active ? "text-blue-400" : "text-gray-500"}>
          {label} {active ? (sortDir === "desc" ? "↓" : "↑") : ""}
        </span>
      </th>
    );
  }

  return (
    <div className="p-6 space-y-5 max-w-5xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Position Intelligence</h1>
        <p className="text-xs text-gray-500 mt-0.5">{data.positions.length} posisi aktif — klik baris untuk analisis detail</p>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 text-xs">
        {(["ALL", "PROFIT", "LOSS", "NO_PRICE"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              filter === f
                ? "bg-gray-700 text-gray-100"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {f === "ALL" && `Semua (${data.positions.length})`}
            {f === "PROFIT" && `Profit`}
            {f === "LOSS" && `Rugi >5% (${lossCount})`}
            {f === "NO_PRICE" && `Tanpa Harga (${noPriceCount})`}
          </button>
        ))}
      </div>

      {noPriceCount > 0 && filter !== "NO_PRICE" && (
        <div className="flex items-center gap-2 text-xs text-amber-400/70">
          <AlertTriangle size={12} />
          {noPriceCount} posisi tidak memiliki data harga terkini — P/L tidak tersedia.
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-800 text-gray-500">
                  <th className="py-2.5 px-4 text-left w-8">#</th>
                  <th className="py-2.5 px-4 text-left">Saham</th>
                  <th className="py-2.5 px-4 text-left">Sektor</th>
                  <SortTh label="Lot" k="lots" />
                  <SortTh label="Avg Cost" k="total_cost" />
                  <th className="py-2.5 px-4 text-right text-gray-500">Harga</th>
                  <SortTh label="P/L" k="pnl_pct" />
                  <SortTh label="Bobot" k="weight" />
                  <th className="py-2.5 px-4 w-8" />
                </tr>
              </thead>
              <tbody>
                {sorted.map((pos, i) => (
                  <PositionRow key={pos.canonical_symbol} pos={pos} rank={i + 1} />
                ))}
                {sorted.length === 0 && (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-xs text-gray-600">
                      Tidak ada posisi yang sesuai filter
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Summary row */}
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div className="bg-gray-800/40 rounded-lg p-3">
          <p className="text-gray-600">Total Modal</p>
          <p className="text-gray-200 font-medium">{formatCurrency(data.total_invested)}</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-3">
          <p className="text-gray-600">Nilai Pasar</p>
          <p className="text-gray-200 font-medium">{formatCurrency(data.market_value)}</p>
        </div>
        <div className={`rounded-lg p-3 ${data.unrealized_pnl >= 0 ? "bg-emerald-900/20" : "bg-red-900/20"}`}>
          <p className="text-gray-600">Unrealized P/L</p>
          <p className={`font-medium ${data.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            {data.unrealized_pnl >= 0 ? "+" : ""}{formatCurrency(data.unrealized_pnl)}
            {" "}({formatPercent(data.unrealized_pnl_pct)})
          </p>
        </div>
      </div>

      <p className="text-xs text-gray-700">Klik nama saham untuk analisis mendalam. Ini bukan nasihat investasi.</p>
    </div>
  );
}
