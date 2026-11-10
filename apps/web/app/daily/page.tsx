"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type DailyIntelligence, type DailyPositionBrief } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, CheckCircle, Clock, TrendingUp, TrendingDown } from "lucide-react";

const ACTION_COLOR: Record<string, string> = {
  BUY: "text-emerald-400",
  ADD_CANDIDATE: "text-emerald-300",
  HOLD: "text-gray-400",
  TRIM_CANDIDATE: "text-amber-400",
  SELL: "text-red-400",
  WAIT: "text-gray-500",
  INSUFFICIENT_DATA: "text-gray-600",
};

const ACTION_LABEL: Record<string, string> = {
  BUY: "Beli",
  ADD_CANDIDATE: "Tambah",
  HOLD: "Tahan",
  TRIM_CANDIDATE: "Kurangi",
  SELL: "Jual",
  WAIT: "Tunggu",
  INSUFFICIENT_DATA: "Data Kurang",
};

const FRESHNESS_BADGE: Record<string, "success" | "warning" | "danger"> = {
  FRESH: "success",
  PARTIAL: "warning",
  STALE: "danger",
};

function PositionRow({ pos }: { pos: DailyPositionBrief }) {
  const router = useRouter();
  const ticker = pos.canonical_symbol.split(":")[1] ?? pos.canonical_symbol;
  const hasPnl = pos.unrealized_pnl_pct !== null;

  return (
    <tr
      className="border-b border-gray-800/50 hover:bg-gray-800/20 cursor-pointer"
      onClick={() => router.push(`/explorer?q=${encodeURIComponent(pos.canonical_symbol)}`)}
    >
      <td className="py-2.5 px-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200">{ticker}</span>
          {pos.data_stale && <Clock size={10} className="text-amber-600" />}
        </div>
        {pos.company_name && <p className="text-xs text-gray-600 truncate max-w-[130px]">{pos.company_name}</p>}
      </td>
      <td className="py-2.5 px-4 text-right text-xs text-gray-400">{pos.lots} lot</td>
      <td className="py-2.5 px-4 text-right text-xs text-gray-400">
        {pos.current_price ? formatCurrency(pos.current_price) : <span className="text-gray-700">—</span>}
      </td>
      <td className="py-2.5 px-4 text-right">
        {hasPnl ? (
          <span className={`text-xs font-medium ${pos.unrealized_pnl_pct! >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            {pos.unrealized_pnl_pct! >= 0 ? "+" : ""}{formatPercent(pos.unrealized_pnl_pct!)}
          </span>
        ) : <span className="text-xs text-gray-700">—</span>}
      </td>
      <td className="py-2.5 px-4 text-right text-xs text-gray-600">
        {(pos.weight * 100).toFixed(1)}%
      </td>
      <td className="py-2.5 px-4 text-center">
        {pos.action ? (
          <span className={`text-xs font-medium ${ACTION_COLOR[pos.action] ?? "text-gray-500"}`}>
            {ACTION_LABEL[pos.action] ?? pos.action}
            {pos.urgency === "REVIEW_NOW" && " ⚡"}
          </span>
        ) : <span className="text-xs text-gray-700">—</span>}
      </td>
    </tr>
  );
}

export default function DailyPage() {
  const [data, setData] = useState<DailyIntelligence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.daily.intelligence()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-6 w-48 bg-gray-800 rounded animate-pulse" />
        <div className="grid grid-cols-3 gap-4">
          {[1,2,3].map(i => <div key={i} className="h-20 bg-gray-800 rounded animate-pulse" />)}
        </div>
        <div className="h-64 bg-gray-800 rounded animate-pulse" />
      </div>
    );
  }

  if (error) return <div className="p-6"><p className="text-red-400 text-sm">{error}</p></div>;
  if (!data) return null;

  const asOf = new Date(data.as_of);
  const asOfStr = asOf.toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });

  return (
    <div className="p-6 space-y-5 max-w-4xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Daily Intelligence</h1>
          <p className="text-xs text-gray-500 mt-0.5">Per {asOfStr}</p>
        </div>
        <Badge variant={FRESHNESS_BADGE[data.data_freshness]}>
          {data.data_freshness === "FRESH" ? "Data Segar" : data.data_freshness === "PARTIAL" ? "Data Sebagian" : "Data Usang"}
        </Badge>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gray-800/50 rounded-lg p-4">
          <p className="text-xs text-gray-600">Posisi</p>
          <p className="text-2xl font-bold text-gray-100">{data.total_positions}</p>
        </div>
        <div className="bg-gray-800/50 rounded-lg p-4">
          <p className="text-xs text-gray-600">Nilai Portofolio</p>
          <p className="text-lg font-bold text-gray-100">{formatCurrency(data.total_market_value)}</p>
        </div>
        <div className={`rounded-lg p-4 ${data.unrealized_pnl_pct >= 0 ? "bg-emerald-900/20" : "bg-red-900/20"}`}>
          <p className="text-xs text-gray-600">Unrealized P/L</p>
          <p className={`text-2xl font-bold ${data.unrealized_pnl_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            {data.unrealized_pnl_pct >= 0 ? "+" : ""}{formatPercent(data.unrealized_pnl_pct)}
          </p>
        </div>
      </div>

      {/* Alerts */}
      {data.alerts.length > 0 && (
        <div className="space-y-2">
          {data.alerts.map((a, i) => (
            <div key={i} className="flex items-start gap-2 rounded-lg bg-amber-950/20 border border-amber-800/30 px-3 py-2">
              <AlertTriangle size={13} className="text-amber-400 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-amber-300/80">{a}</p>
            </div>
          ))}
        </div>
      )}

      {data.alerts.length === 0 && data.total_positions > 0 && (
        <div className="flex items-center gap-2 rounded-lg bg-emerald-950/20 border border-emerald-800/30 px-3 py-2">
          <CheckCircle size={13} className="text-emerald-400" />
          <p className="text-xs text-emerald-300/70">Tidak ada alert hari ini — portofolio dalam kondisi normal</p>
        </div>
      )}

      {/* Positions table */}
      {data.positions.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-800 text-gray-500">
                    <th className="py-2.5 px-4 text-left">Saham</th>
                    <th className="py-2.5 px-4 text-right">Lot</th>
                    <th className="py-2.5 px-4 text-right">Harga</th>
                    <th className="py-2.5 px-4 text-right">P/L</th>
                    <th className="py-2.5 px-4 text-right">Bobot</th>
                    <th className="py-2.5 px-4 text-center">Sinyal</th>
                  </tr>
                </thead>
                <tbody>
                  {data.positions.map((pos) => (
                    <PositionRow key={pos.canonical_symbol} pos={pos} />
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {data.total_positions === 0 && (
        <div className="text-center py-12 text-gray-600 text-sm">
          Belum ada posisi — seed portofolio atau tambahkan transaksi manual
        </div>
      )}

      <p className="text-xs text-gray-700">
        Sinyal dari engine rekomendasi deterministik. Bukan nasihat investasi.
        {data.data_freshness !== "FRESH" && " Data harga mungkin tidak terkini."}
      </p>
    </div>
  );
}
