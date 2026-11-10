"use client";

import React, { useEffect, useState } from "react";
import { api, type DecisionSummary, type DecisionList } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { RefreshCw, AlertTriangle, TrendingUp, TrendingDown, Minus, ChevronDown, ChevronUp } from "lucide-react";

const ACTION_VARIANT: Record<string, "success" | "danger" | "warning" | "default"> = {
  BUY: "success",
  ADD_CANDIDATE: "success",
  HOLD: "default",
  WAIT: "default",
  TRIM_CANDIDATE: "warning",
  SELL: "danger",
  INSUFFICIENT_DATA: "default",
};

const ACTION_LABEL: Record<string, string> = {
  BUY: "Beli",
  ADD_CANDIDATE: "Tambah",
  HOLD: "Tahan",
  WAIT: "Tunggu",
  TRIM_CANDIDATE: "Kurangi",
  SELL: "Jual",
  INSUFFICIENT_DATA: "Data Kurang",
};

const CONFIDENCE_COLOR: Record<string, string> = {
  HIGH: "text-emerald-400",
  MEDIUM: "text-amber-400",
  LOW: "text-gray-500",
};

function ScoreBar({ score }: { score: number }) {
  const color = score >= 60 ? "bg-emerald-500" : score >= 45 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(100, score)}%` }} />
      </div>
      <span className="text-xs text-gray-400 w-8 text-right">{score.toFixed(0)}</span>
    </div>
  );
}

function DecisionCard({ d }: { d: DecisionSummary }) {
  const [expanded, setExpanded] = useState(false);
  const ticker = d.canonical_symbol.split(":")[1] ?? d.canonical_symbol;
  const isUrgent = d.urgency === "REVIEW_NOW";
  const hasGateBlock = d.hard_gate_status !== "PASS";

  return (
    <Card className={isUrgent ? "border-amber-700/40" : ""}>
      <CardContent className="py-3 px-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-gray-100">{ticker}</span>
            <Badge variant={ACTION_VARIANT[d.action]}>{ACTION_LABEL[d.action] ?? d.action}</Badge>
            {d.owned && (
              <span className="text-xs text-blue-400 bg-blue-900/20 px-1.5 py-0.5 rounded">
                {d.portfolio_weight?.toFixed(1)}% porto
              </span>
            )}
            {isUrgent && (
              <span className="flex items-center gap-1 text-xs text-amber-400">
                <AlertTriangle size={11} /> Review
              </span>
            )}
          </div>
          <div className="text-right shrink-0">
            {d.current_price != null && (
              <p className="text-xs text-gray-400">Rp {d.current_price.toLocaleString("id-ID")}</p>
            )}
            <p className={`text-xs ${CONFIDENCE_COLOR[d.evidence_confidence]}`}>
              {d.evidence_confidence}
            </p>
          </div>
        </div>

        {/* Score bar */}
        {!hasGateBlock && <ScoreBar score={d.composite_score} />}

        {/* Gate block message */}
        {hasGateBlock && d.hard_gate_reason && (
          <p className="text-xs text-gray-500 italic">{d.hard_gate_reason}</p>
        )}

        {/* Factor scores mini row */}
        {!hasGateBlock && (
          <div className="flex gap-3 text-xs text-gray-500">
            {Object.entries(d.factor_scores).map(([k, v]) => (
              <span key={k}>
                {k.slice(0, 4).toUpperCase()}: <span className="text-gray-300">{v?.toFixed(0) ?? "—"}</span>
              </span>
            ))}
          </div>
        )}

        {/* Expandable thesis */}
        {(d.bull_thesis.length > 0 || d.bear_case.length > 0) && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-600 hover:text-gray-400 flex items-center gap-1"
          >
            {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            {expanded ? "Tutup" : "Lihat tesis"}
          </button>
        )}

        {expanded && (
          <div className="space-y-2 pt-1 border-t border-gray-800/50">
            {d.bull_thesis.length > 0 && (
              <div>
                <p className="text-xs font-medium text-emerald-500 mb-1 flex items-center gap-1">
                  <TrendingUp size={10} /> Bull
                </p>
                <ul className="space-y-0.5">
                  {d.bull_thesis.map((b, i) => (
                    <li key={i} className="text-xs text-gray-400">• {b}</li>
                  ))}
                </ul>
              </div>
            )}
            {d.bear_case.length > 0 && (
              <div>
                <p className="text-xs font-medium text-red-500 mb-1 flex items-center gap-1">
                  <TrendingDown size={10} /> Bear
                </p>
                <ul className="space-y-0.5">
                  {d.bear_case.map((b, i) => (
                    <li key={i} className="text-xs text-gray-400">• {b}</li>
                  ))}
                </ul>
              </div>
            )}
            {d.data_gaps.length > 0 && (
              <p className="text-xs text-gray-600">Data gap: {d.data_gaps.join(", ")}</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const FILTERS = ["ALL", "BUY", "ADD_CANDIDATE", "HOLD", "TRIM_CANDIDATE", "SELL", "WAIT", "INSUFFICIENT_DATA"] as const;
const FILTER_LABEL: Record<string, string> = {
  ALL: "Semua", BUY: "Beli", ADD_CANDIDATE: "Tambah", HOLD: "Tahan",
  TRIM_CANDIDATE: "Kurangi", SELL: "Jual", WAIT: "Tunggu", INSUFFICIENT_DATA: "Data Kurang",
};

export default function DecisionsPage() {
  const [data, setData] = useState<DecisionList | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("ALL");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.decisions.list();
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const decisions = data?.decisions ?? [];
  const filtered = filter === "ALL" ? decisions : decisions.filter(d => d.action === filter);

  const counts = data?.action_counts ?? {};
  const reviewNow = decisions.filter(d => d.urgency === "REVIEW_NOW").length;

  return (
    <div className="p-6 space-y-5 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Decisions</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Sinyal dari decision engine — deterministik, bukan rekomendasi investasi
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="p-2 text-gray-500 hover:text-gray-300 disabled:opacity-40 transition-colors"
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* KPI row */}
      {data && (
        <div className="grid grid-cols-4 gap-2 text-xs">
          {[
            { label: "Beli / Tambah", val: (counts.BUY ?? 0) + (counts.ADD_CANDIDATE ?? 0), color: "text-emerald-400" },
            { label: "Tahan", val: counts.HOLD ?? 0, color: "text-gray-300" },
            { label: "Kurangi / Jual", val: (counts.TRIM_CANDIDATE ?? 0) + (counts.SELL ?? 0), color: "text-red-400" },
            { label: "Review Sekarang", val: reviewNow, color: "text-amber-400" },
          ].map(({ label, val, color }) => (
            <div key={label} className="bg-gray-800/50 rounded-lg p-2.5 text-center">
              <p className="text-gray-600">{label}</p>
              <p className={`text-xl font-bold ${color}`}>{val}</p>
            </div>
          ))}
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex flex-wrap gap-1.5 text-xs">
        {FILTERS.map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-2.5 py-1 rounded-md transition-colors ${
              filter === f ? "bg-gray-700 text-gray-100" : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {FILTER_LABEL[f]}{f !== "ALL" && counts[f] ? ` (${counts[f]})` : f === "ALL" && data ? ` (${data.total})` : ""}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <div key={i} className="h-20 bg-gray-800 rounded-lg animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 space-y-3">
          <Minus size={28} className="mx-auto text-gray-700" />
          {decisions.length === 0 ? (
            <>
              <p className="text-sm text-gray-400 font-medium">Belum ada saham untuk dianalisis</p>
              <p className="text-xs text-gray-600 max-w-xs mx-auto leading-relaxed">
                Decision Center menganalisis saham di portofolio dan watchlist-mu.
                Tambahkan saham terlebih dahulu.
              </p>
              <div className="flex justify-center gap-2 mt-2">
                <a href="/portfolio" className="text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors">
                  Buka Portofolio
                </a>
                <a href="/watchlist" className="text-xs px-3 py-1.5 bg-indigo-700 hover:bg-indigo-600 text-white rounded-lg transition-colors">
                  Buka Watchlist
                </a>
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-600">Tidak ada sinyal untuk filter yang dipilih</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(d => (
            <DecisionCard key={d.instrument_id} d={d} />
          ))}
        </div>
      )}

      <p className="text-xs text-gray-700">
        Sinyal dihitung dari data fundamental & teknikal. Bukan rekomendasi investasi.
        Selalu lakukan riset mandiri sebelum mengambil keputusan.
      </p>
    </div>
  );
}
