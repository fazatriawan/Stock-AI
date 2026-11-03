"use client";

import React, { useEffect, useState } from "react";
import { api, type RebalanceSimulation, type CapitalAllocationPlan, type TargetAllocation } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TrendingUp, TrendingDown, Minus, RefreshCw, AlertTriangle, Info } from "lucide-react";

type Mode = "equal_weight" | "capital_plan";

const ACTION_STYLE: Record<string, { badge: "success" | "danger" | "default"; icon: React.ReactElement; label: string }> = {
  BUY: { badge: "success", icon: <TrendingUp size={12} />, label: "Beli" },
  SELL: { badge: "danger", icon: <TrendingDown size={12} />, label: "Jual" },
  HOLD: { badge: "default", icon: <Minus size={12} />, label: "Tahan" },
};

function formatLots(lots: number) {
  if (lots === 0) return "—";
  return `${lots > 0 ? "+" : ""}${lots} lot`;
}

function AllocationRow({ a }: { a: TargetAllocation }) {
  const ticker = a.canonical_symbol.split(":")[1] ?? a.canonical_symbol;
  const style = ACTION_STYLE[a.action];
  const weightDelta = a.target_weight - a.current_weight;

  return (
    <tr className="border-b border-gray-800/50 hover:bg-gray-800/20">
      <td className="py-3 px-4">
        <p className="text-sm font-medium text-gray-200">{ticker}</p>
        {a.company_name && <p className="text-xs text-gray-600 truncate max-w-[120px]">{a.company_name}</p>}
      </td>
      <td className="py-3 px-4 text-center">
        <Badge variant={style.badge} className="gap-1">
          {style.icon}{style.label}
        </Badge>
      </td>
      <td className="py-3 px-4 text-right text-xs text-gray-400">{a.current_lots} lot</td>
      <td className="py-3 px-4 text-right">
        <div>
          <span className="text-xs text-gray-400">{(a.current_weight * 100).toFixed(1)}%</span>
          <span className="text-xs text-gray-600 mx-1">→</span>
          <span className="text-xs text-gray-200">{(a.target_weight * 100).toFixed(1)}%</span>
        </div>
        <div className={`text-xs ${weightDelta > 0 ? "text-emerald-500" : weightDelta < 0 ? "text-red-500" : "text-gray-600"}`}>
          {weightDelta !== 0 ? `${weightDelta > 0 ? "+" : ""}${(weightDelta * 100).toFixed(1)}%` : ""}
        </div>
      </td>
      <td className="py-3 px-4 text-right">
        <p className={`text-sm font-medium ${a.delta_lots > 0 ? "text-emerald-400" : a.delta_lots < 0 ? "text-red-400" : "text-gray-600"}`}>
          {formatLots(a.delta_lots)}
        </p>
        {a.delta_value !== 0 && (
          <p className="text-xs text-gray-600">{formatCurrency(Math.abs(a.delta_value))}</p>
        )}
      </td>
      <td className="py-3 px-4 text-xs text-gray-600 max-w-[200px]">{a.note}</td>
    </tr>
  );
}

export default function RebalancePage() {
  const [mode, setMode] = useState<Mode>("equal_weight");
  const [newCapital, setNewCapital] = useState<string>("");
  const [simulation, setSimulation] = useState<RebalanceSimulation | null>(null);
  const [capitalPlan, setCapitalPlan] = useState<CapitalAllocationPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSimulation() {
    setLoading(true);
    setError(null);
    try {
      const capital = parseFloat(newCapital.replace(/[,.]/g, "")) || 0;
      if (mode === "equal_weight") {
        const result = await api.portfolio.simulateRebalance({}, capital);
        setSimulation(result);
        setCapitalPlan(null);
      } else {
        if (capital <= 0) {
          setError("Masukkan jumlah modal yang ingin dialokasikan");
          return;
        }
        const result = await api.portfolio.planAllocation(capital);
        setCapitalPlan(result);
        setSimulation(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Terjadi kesalahan");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Rebalance Simulator</h1>
        <p className="text-xs text-gray-500 mt-0.5">Simulasi alokasi modal — tidak ada transaksi nyata yang dieksekusi</p>
      </div>

      {/* Mode selector + input */}
      <Card>
        <CardContent className="pt-5 pb-5 space-y-4">
          {/* Mode tabs */}
          <div className="flex gap-2">
            <button
              onClick={() => setMode("equal_weight")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                mode === "equal_weight"
                  ? "bg-blue-900/40 border border-blue-700/40 text-blue-300"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              Equal Weight
            </button>
            <button
              onClick={() => setMode("capital_plan")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                mode === "capital_plan"
                  ? "bg-blue-900/40 border border-blue-700/40 text-blue-300"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              Alokasi Modal Baru
            </button>
          </div>

          <p className="text-xs text-gray-600">
            {mode === "equal_weight"
              ? "Simulasikan rebalancing ke bobot equal-weight (1/n per saham). Tambahkan modal baru opsional."
              : "Rencanakan cara mengalokasikan modal baru ke posisi yang underweight."}
          </p>

          {/* Capital input */}
          <div className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="block text-xs text-gray-400 mb-1.5">
                {mode === "equal_weight" ? "Modal tambahan (opsional)" : "Modal baru (wajib)"}
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-xs text-gray-600">Rp</span>
                <input
                  type="text"
                  value={newCapital}
                  onChange={(e) => setNewCapital(e.target.value)}
                  placeholder="0"
                  className="w-full bg-gray-800 border border-gray-700 rounded-md pl-8 pr-4 py-2 text-sm text-gray-100 focus:outline-none focus:border-gray-500"
                />
              </div>
            </div>
            <Button onClick={runSimulation} disabled={loading} className="shrink-0">
              {loading ? (
                <><RefreshCw size={14} className="animate-spin mr-1" />Menghitung...</>
              ) : (
                "Simulasikan"
              )}
            </Button>
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}
        </CardContent>
      </Card>

      {/* Equal weight simulation result */}
      {simulation && (
        <div className="space-y-4">
          {/* Summary stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="bg-gray-800/50 rounded-lg p-3 text-center">
              <p className="text-gray-600">Total Nilai</p>
              <p className="text-gray-200 font-medium">{formatCurrency(simulation.total_portfolio_value)}</p>
            </div>
            <div className="bg-emerald-900/20 rounded-lg p-3 text-center">
              <p className="text-gray-600">Beli</p>
              <p className="text-emerald-400 font-medium">{simulation.buy_actions} aksi</p>
              <p className="text-emerald-600">{formatCurrency(simulation.total_buy_value)}</p>
            </div>
            <div className="bg-red-900/20 rounded-lg p-3 text-center">
              <p className="text-gray-600">Jual</p>
              <p className="text-red-400 font-medium">{simulation.sell_actions} aksi</p>
              <p className="text-red-600">{formatCurrency(simulation.total_sell_value)}</p>
            </div>
            <div className={`rounded-lg p-3 text-center ${simulation.net_cash_needed > 0 ? "bg-amber-900/20" : "bg-gray-800/50"}`}>
              <p className="text-gray-600">{simulation.net_cash_needed > 0 ? "Modal Dibutuhkan" : "Sisa Kas"}</p>
              <p className={`font-medium ${simulation.net_cash_needed > 0 ? "text-amber-400" : "text-gray-300"}`}>
                {formatCurrency(Math.abs(simulation.net_cash_needed))}
              </p>
            </div>
          </div>

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-800 text-gray-500">
                      <th className="py-2.5 px-4 text-left">Saham</th>
                      <th className="py-2.5 px-4 text-center">Aksi</th>
                      <th className="py-2.5 px-4 text-right">Saat ini</th>
                      <th className="py-2.5 px-4 text-right">Bobot</th>
                      <th className="py-2.5 px-4 text-right">Delta</th>
                      <th className="py-2.5 px-4 text-left">Keterangan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {simulation.allocations.map((a) => (
                      <AllocationRow key={a.canonical_symbol} a={a} />
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <div className="flex items-start gap-2 rounded-lg bg-gray-800/30 border border-gray-700/30 px-4 py-3">
            <Info size={13} className="text-gray-600 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-gray-600">{simulation.disclaimer}</p>
          </div>
        </div>
      )}

      {/* Capital allocation plan result */}
      {capitalPlan && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="bg-blue-900/20 rounded-lg p-3 text-center">
              <p className="text-gray-600">Modal Dialokasikan</p>
              <p className="text-blue-300 font-medium">{formatCurrency(capitalPlan.new_capital)}</p>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3 text-center">
              <p className="text-gray-600">Saran Posisi</p>
              <p className="text-gray-200 font-medium">{capitalPlan.suggestions.length}</p>
            </div>
          </div>

          {capitalPlan.undiversified_warning && (
            <div className="flex items-center gap-2 text-xs text-amber-400/70">
              <AlertTriangle size={12} />
              {capitalPlan.undiversified_warning}
            </div>
          )}

          <div className="space-y-2">
            {capitalPlan.suggestions.map((s) => {
              const ticker = s.canonical_symbol.split(":")[1] ?? s.canonical_symbol;
              return (
                <div key={s.canonical_symbol} className="rounded-lg border border-gray-700/40 bg-gray-800/20 px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-600 w-5 text-right">{s.priority}</span>
                      <div>
                        <p className="text-sm font-medium text-gray-200">{ticker}</p>
                        {s.company_name && <p className="text-xs text-gray-600">{s.company_name}</p>}
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium text-emerald-400">+{s.suggested_lots} lot</p>
                      <p className="text-xs text-gray-500">{formatCurrency(s.suggested_new_amount)}</p>
                    </div>
                  </div>
                  <p className="text-xs text-gray-600 mt-1.5 ml-8">{s.rationale}</p>
                </div>
              );
            })}
            {capitalPlan.suggestions.length === 0 && (
              <p className="text-xs text-gray-600 text-center py-4">
                Semua posisi sudah mendekati equal-weight — tidak ada saran alokasi spesifik
              </p>
            )}
          </div>

          <div className="flex items-start gap-2 rounded-lg bg-gray-800/30 border border-gray-700/30 px-4 py-3">
            <Info size={13} className="text-gray-600 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-gray-600">{capitalPlan.disclaimer}</p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!simulation && !capitalPlan && !loading && (
        <div className="text-center py-12 text-gray-600 text-sm">
          Pilih mode dan klik Simulasikan untuk memulai
        </div>
      )}
    </div>
  );
}
