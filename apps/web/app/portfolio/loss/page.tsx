"use client";

import { useEffect, useState } from "react";
import { api, type LossAnalysis, type LossPosition, type LossScenario } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingDown, AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";

const SCENARIO_COLORS: Record<string, string> = {
  CUT_LOSS: "border-red-800/40 bg-red-950/20",
  PARTIAL_CUT: "border-amber-800/40 bg-amber-950/20",
  HOLD_WAIT: "border-gray-700/40 bg-gray-800/20",
  AVERAGE_DOWN: "border-blue-800/40 bg-blue-950/20",
  STOP_LOSS: "border-purple-800/40 bg-purple-950/20",
};

const RISK_BADGES: Record<string, "danger" | "warning" | "success"> = {
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "success",
};

function ScenarioCard({ scenario, isSuggested }: { scenario: LossScenario; isSuggested: boolean }) {
  const [expanded, setExpanded] = useState(isSuggested);
  const borderClass = SCENARIO_COLORS[scenario.scenario] ?? "border-gray-700";

  return (
    <div className={`rounded-lg border ${borderClass} overflow-hidden`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200">{scenario.label}</span>
          {isSuggested && <Badge variant="success" className="text-xs">Disarankan</Badge>}
        </div>
        <div className="flex items-center gap-3">
          <Badge variant={RISK_BADGES[scenario.risk_level]}>Risiko {scenario.risk_level === "LOW" ? "Rendah" : scenario.risk_level === "MEDIUM" ? "Sedang" : "Tinggi"}</Badge>
          {expanded ? <ChevronUp size={14} className="text-gray-500" /> : <ChevronDown size={14} className="text-gray-500" />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/5">
          <p className="text-xs text-gray-400 mt-3">{scenario.description}</p>

          <div className="grid grid-cols-2 gap-3 text-xs">
            {scenario.projected_loss_idr !== 0 && (
              <div>
                <p className="text-gray-600">Realisasi kerugian</p>
                <p className="text-red-400 font-medium">{formatCurrency(scenario.projected_loss_idr)}</p>
              </div>
            )}
            <div>
              <p className="text-gray-600">Sisa eksposur</p>
              <p className="text-gray-300 font-medium">{formatCurrency(scenario.remaining_exposure_idr)}</p>
            </div>
            {scenario.breakeven_price !== null && (
              <div>
                <p className="text-gray-600">Harga impas</p>
                <p className="text-gray-300 font-medium">{formatCurrency(scenario.breakeven_price)}</p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <p className="text-xs font-medium text-emerald-500">Kelebihan</p>
              {scenario.pros.map((p, i) => (
                <p key={i} className="text-xs text-gray-500 flex gap-1">
                  <span className="text-emerald-700">+</span>{p}
                </p>
              ))}
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-red-500">Kekurangan</p>
              {scenario.cons.map((c, i) => (
                <p key={i} className="text-xs text-gray-500 flex gap-1">
                  <span className="text-red-700">−</span>{c}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function LossPositionCard({ position }: { position: LossPosition }) {
  const [showScenarios, setShowScenarios] = useState(false);
  const ticker = position.canonical_symbol.split(":")[1] ?? position.canonical_symbol;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base text-gray-100">{ticker}</CardTitle>
            {position.company_name && (
              <p className="text-xs text-gray-500 mt-0.5">{position.company_name}</p>
            )}
          </div>
          <div className="text-right">
            <p className="text-lg font-bold text-red-400">
              {formatPercent(position.unrealized_pnl_pct)}
            </p>
            <p className="text-xs text-red-500">{formatCurrency(position.unrealized_pnl)}</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stats grid */}
        <div className="grid grid-cols-3 gap-3 text-xs">
          <div>
            <p className="text-gray-600">Avg cost</p>
            <p className="text-gray-300">{formatCurrency(position.avg_cost)}</p>
          </div>
          <div>
            <p className="text-gray-600">Harga saat ini</p>
            <p className="text-gray-300">{formatCurrency(position.current_price)}</p>
          </div>
          <div>
            <p className="text-gray-600">Lot / Saham</p>
            <p className="text-gray-300">{position.lots} / {position.shares.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-gray-600">Modal</p>
            <p className="text-gray-300">{formatCurrency(position.total_cost)}</p>
          </div>
          <div>
            <p className="text-gray-600">Nilai pasar</p>
            <p className="text-gray-300">{formatCurrency(position.market_value)}</p>
          </div>
          <div>
            <p className="text-gray-600">Rugi (IDR)</p>
            <p className="text-red-400">{formatCurrency(position.unrealized_pnl)}</p>
          </div>
        </div>

        {/* Saran */}
        <div className="rounded-lg bg-blue-950/20 border border-blue-800/30 px-3 py-2.5">
          <p className="text-xs text-gray-500 mb-1">Skenario disarankan</p>
          <p className="text-xs font-medium text-blue-300">{position.suggested_reason}</p>
        </div>

        {/* Toggle scenarios */}
        <button
          onClick={() => setShowScenarios(!showScenarios)}
          className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
        >
          {showScenarios ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {showScenarios ? "Sembunyikan" : "Lihat"} 5 skenario aksi
        </button>

        {showScenarios && (
          <div className="space-y-2">
            {position.scenarios.map((s) => (
              <ScenarioCard
                key={s.scenario}
                scenario={s}
                isSuggested={s.scenario === position.suggested_scenario}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function LossAnalyzerPage() {
  const [data, setData] = useState<LossAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.portfolio.lossAnalysis()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-6 w-48 bg-gray-800 rounded animate-pulse" />
        {[1, 2].map((i) => <div key={i} className="h-48 bg-gray-800 rounded-lg animate-pulse" />)}
      </div>
    );
  }

  if (error) {
    return <div className="p-6"><p className="text-red-400 text-sm">{error}</p></div>;
  }

  if (!data) return null;

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Loss Analyzer</h1>
        <p className="text-xs text-gray-500 mt-0.5">Analisis posisi rugi dengan 5 skenario aksi deterministik</p>
      </div>

      {/* Summary */}
      {data.total_loss_positions > 0 && (
        <div className="flex gap-4">
          <div className="bg-red-900/20 border border-red-800/30 rounded-lg p-4 flex-1 text-center">
            <p className="text-xs text-gray-500">Posisi Rugi</p>
            <p className="text-2xl font-bold text-red-400">{data.total_loss_positions}</p>
          </div>
          <div className="bg-red-900/20 border border-red-800/30 rounded-lg p-4 flex-1 text-center">
            <p className="text-xs text-gray-500">Total Unrealized Loss</p>
            <p className="text-xl font-bold text-red-400">{formatCurrency(data.total_unrealized_loss_idr)}</p>
          </div>
        </div>
      )}

      {data.loss_positions.length === 0 ? (
        <div className="rounded-xl border border-emerald-800/30 bg-emerald-900/10 p-8 text-center">
          <TrendingDown size={32} className="mx-auto text-emerald-400 mb-3" />
          <p className="text-sm font-medium text-emerald-300">Tidak ada posisi rugi signifikan</p>
          <p className="text-xs text-gray-500 mt-1">Semua posisi rugi &lt;5% atau tidak memiliki data harga terkini</p>
        </div>
      ) : (
        <div className="space-y-4">
          {data.loss_positions.map((pos) => (
            <LossPositionCard key={pos.canonical_symbol} position={pos} />
          ))}
        </div>
      )}

      <p className="text-xs text-gray-700">
        Skenario dihitung dari data posisi saat ini. Ini bukan nasihat investasi.
        Keputusan jual/beli sepenuhnya menjadi tanggung jawab pengguna.
      </p>
    </div>
  );
}
