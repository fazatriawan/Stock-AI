"use client";

import { useEffect, useState } from "react";
import { api, type PortfolioHealth } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, CheckCircle, TrendingUp, Shield, PieChart } from "lucide-react";

const GRADE_COLORS: Record<string, string> = {
  EXCELLENT: "text-emerald-400",
  GOOD: "text-blue-400",
  FAIR: "text-amber-400",
  POOR: "text-red-400",
};

const GRADE_BG: Record<string, string> = {
  EXCELLENT: "bg-emerald-900/20 border-emerald-800/40",
  GOOD: "bg-blue-900/20 border-blue-800/40",
  FAIR: "bg-amber-900/20 border-amber-800/40",
  POOR: "bg-red-900/20 border-red-800/40",
};

const GRADE_LABEL: Record<string, string> = {
  EXCELLENT: "Sangat Baik",
  GOOD: "Baik",
  FAIR: "Cukup",
  POOR: "Perlu Perhatian",
};

function ScoreBar({ value, max = 100, color = "bg-blue-500" }: { value: number; max?: number; color?: string }) {
  return (
    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${color}`}
        style={{ width: `${Math.min(100, (value / max) * 100)}%` }}
      />
    </div>
  );
}

function ComponentCard({ label, score, max, description }: {
  label: string; score: number; max: number; description: string;
}) {
  const pct = score / max;
  const color = pct >= 0.8 ? "bg-emerald-500" : pct >= 0.6 ? "bg-blue-500" : pct >= 0.4 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="bg-gray-800/50 rounded-lg p-4 space-y-2">
      <div className="flex justify-between items-baseline">
        <span className="text-xs text-gray-400">{label}</span>
        <span className="text-sm font-semibold text-gray-100">{score.toFixed(1)} / {max}</span>
      </div>
      <ScoreBar value={score} max={max} color={color} />
      <p className="text-xs text-gray-600">{description}</p>
    </div>
  );
}

export default function PortfolioHealthPage() {
  const [data, setData] = useState<PortfolioHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.portfolio.health()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-6 w-48 bg-gray-800 rounded animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <div key={i} className="h-32 bg-gray-800 rounded-lg animate-pulse" />)}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  const gradeColor = GRADE_COLORS[data.grade] ?? "text-gray-400";
  const gradeBg = GRADE_BG[data.grade] ?? "";

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Portfolio Health</h1>
        <p className="text-xs text-gray-500 mt-0.5">Analisis konsentrasi, diversifikasi, dan kondisi portofolio</p>
      </div>

      {/* Health Score Card */}
      <div className={`rounded-xl border p-6 ${gradeBg}`}>
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-gray-500 mb-1">Health Score</p>
            <p className={`text-5xl font-bold ${gradeColor}`}>{data.health_score.toFixed(0)}</p>
            <p className={`text-sm font-medium mt-1 ${gradeColor}`}>{GRADE_LABEL[data.grade]}</p>
          </div>
          <div className="text-right space-y-1">
            <p className="text-xs text-gray-500">{data.position_count} posisi</p>
            <p className="text-xs text-gray-500">Diversifikasi: {data.diversification_score.toFixed(0)}/100</p>
            <p className={`text-xs font-medium ${data.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              P/L: {data.unrealized_pnl >= 0 ? "+" : ""}{formatPercent(data.unrealized_pnl_pct)}
            </p>
          </div>
        </div>

        {/* Score breakdown bar */}
        <div className="mt-4 h-2 bg-black/20 rounded-full overflow-hidden flex">
          <div className="bg-emerald-600/60 h-full" style={{ width: `${data.diversification_component}%` }} title={`Diversifikasi: ${data.diversification_component.toFixed(1)}`} />
          <div className="bg-blue-600/60 h-full" style={{ width: `${data.concentration_component}%` }} title={`Konsentrasi: ${data.concentration_component.toFixed(1)}`} />
          <div className="bg-amber-600/60 h-full" style={{ width: `${data.pnl_component}%` }} title={`P/L: ${data.pnl_component.toFixed(1)}`} />
        </div>
        <div className="flex gap-4 mt-2 text-xs text-gray-600">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-600/60 inline-block" />Diversifikasi</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-600/60 inline-block" />Konsentrasi</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-600/60 inline-block" />P/L</span>
        </div>
      </div>

      {/* Komponen skor */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ComponentCard
          label="Diversifikasi"
          score={data.diversification_component}
          max={40}
          description="Berdasarkan Herfindahl Index — semakin merata bobot posisi, semakin tinggi."
        />
        <ComponentCard
          label="Konsentrasi"
          score={data.concentration_component}
          max={30}
          description="Berkurang jika ada posisi > 25% (overweight) atau > 40% (severely overweight)."
        />
        <ComponentCard
          label="Kinerja P/L"
          score={data.pnl_component}
          max={30}
          description="Berdasarkan unrealized P/L keseluruhan portofolio saat ini."
        />
      </div>

      {/* Risiko konsentrasi */}
      {data.concentration_risks.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <AlertTriangle size={14} className="text-amber-400" />
              Risiko Konsentrasi
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.concentration_risks.map((r) => (
              <div key={r.symbol} className="flex items-center justify-between rounded-lg bg-amber-900/10 border border-amber-800/30 px-4 py-2.5">
                <div>
                  <span className="text-sm font-medium text-gray-200">{r.symbol.split(":")[1] ?? r.symbol}</span>
                  <p className="text-xs text-gray-500 mt-0.5">{r.message}</p>
                </div>
                <Badge variant={r.severity === "SEVERELY_OVERWEIGHT" ? "danger" : "warning"}>
                  {(r.weight * 100).toFixed(1)}%
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Risiko sektor */}
      {data.sector_risks.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <PieChart size={14} className="text-amber-400" />
              Konsentrasi Sektor
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.sector_risks.map((r) => (
              <div key={r.sector} className="flex items-center justify-between rounded-lg bg-amber-900/10 border border-amber-800/30 px-4 py-2.5">
                <p className="text-sm text-gray-300">{r.message}</p>
                <Badge variant="warning">{(r.weight * 100).toFixed(1)}%</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Warnings */}
      {data.warnings.length > 0 && (
        <div className="space-y-2">
          {data.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-amber-300/80">
              <AlertTriangle size={12} className="mt-0.5 flex-shrink-0 text-amber-400" />
              {w}
            </div>
          ))}
        </div>
      )}

      {/* Rekomendasi */}
      {data.recommendations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <CheckCircle size={14} className="text-emerald-400" />
              Rekomendasi
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.recommendations.map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-gray-400">
                <span className="text-emerald-600 font-bold mt-0.5">→</span>
                {r}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {data.warnings.length === 0 && data.concentration_risks.length === 0 && data.sector_risks.length === 0 && (
        <div className="flex items-center gap-3 rounded-lg bg-emerald-900/10 border border-emerald-800/30 px-4 py-3">
          <CheckCircle size={16} className="text-emerald-400 flex-shrink-0" />
          <p className="text-sm text-emerald-300/80">Portofolio dalam kondisi sehat — tidak ada risiko konsentrasi yang terdeteksi.</p>
        </div>
      )}

      <p className="text-xs text-gray-700">
        Skor dihitung deterministik dari data posisi. Ini bukan nasihat investasi.
        Keputusan sepenuhnya tanggung jawab pengguna.
      </p>
    </div>
  );
}
