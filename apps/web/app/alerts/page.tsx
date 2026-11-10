"use client";

import React, { useEffect, useState } from "react";
import {
  api,
  type AlertRuleResponse,
  type AlertEvalResponse,
  type AlertHistoryItem,
  type AlertRuleCreateRequest,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const RULE_TYPES = [
  "price_above", "price_below",
  "pct_change_1d_above", "pct_change_1d_below",
  "rsi_above", "rsi_below",
  "swing_breakout", "swing_pullback",
  "macro_inverted",
];

// Label & deskripsi ramah pengguna untuk setiap tipe alert
const RULE_META: Record<string, { label: string; desc: string; thresholdLabel?: string; thresholdPlaceholder?: string }> = {
  price_above:          { label: "Harga naik di atas batas", desc: "Notifikasi saat harga saham melewati nilai tertentu ke atas", thresholdLabel: "Batas Harga (Rp)", thresholdPlaceholder: "mis. 5000" },
  price_below:          { label: "Harga turun di bawah batas", desc: "Notifikasi saat harga saham jatuh di bawah nilai tertentu", thresholdLabel: "Batas Harga (Rp)", thresholdPlaceholder: "mis. 3000" },
  pct_change_1d_above:  { label: "Naik lebih dari X% hari ini", desc: "Notifikasi saat saham naik signifikan dalam sehari", thresholdLabel: "Persen Kenaikan (%)", thresholdPlaceholder: "mis. 5" },
  pct_change_1d_below:  { label: "Turun lebih dari X% hari ini", desc: "Notifikasi saat saham turun tajam dalam sehari", thresholdLabel: "Persen Penurunan (%)", thresholdPlaceholder: "mis. -5" },
  rsi_above:            { label: "RSI memasuki area jenuh beli", desc: "RSI di atas ambang = saham mungkin overbought (terlalu mahal)", thresholdLabel: "Batas RSI (0-100)", thresholdPlaceholder: "mis. 70" },
  rsi_below:            { label: "RSI memasuki area jenuh jual", desc: "RSI di bawah ambang = saham mungkin oversold (terlalu murah)", thresholdLabel: "Batas RSI (0-100)", thresholdPlaceholder: "mis. 30" },
  swing_breakout:       { label: "Breakout — potensi kenaikan", desc: "Harga menembus resistance dengan volume, bisa jadi sinyal beli", thresholdLabel: undefined, thresholdPlaceholder: undefined },
  swing_pullback:       { label: "Pullback — koreksi dari puncak", desc: "Harga menarik kembali setelah naik, mungkin peluang beli ulang", thresholdLabel: undefined, thresholdPlaceholder: undefined },
  macro_inverted:       { label: "Yield curve terbalik", desc: "Obligasi jangka pendek lebih tinggi dari panjang — sinyal resesi", thresholdLabel: undefined, thresholdPlaceholder: undefined },
};

const NEEDS_SYMBOL = new Set(RULE_TYPES.filter(r => r !== "macro_inverted"));
const NEEDS_THRESHOLD = new Set([
  "price_above", "price_below",
  "pct_change_1d_above", "pct_change_1d_below",
  "rsi_above", "rsi_below",
]);

function fmtDatetime(d: string | null): string {
  if (!d) return "—";
  return new Date(d).toLocaleString("id-ID", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function RuleTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    price_above: "bg-emerald-900/30 text-emerald-400 border-emerald-800/40",
    price_below: "bg-red-900/30 text-red-400 border-red-800/40",
    pct_change_1d_above: "bg-emerald-900/20 text-emerald-500 border-emerald-800/30",
    pct_change_1d_below: "bg-red-900/20 text-red-500 border-red-800/30",
    rsi_above: "bg-orange-900/30 text-orange-400 border-orange-800/40",
    rsi_below: "bg-cyan-900/30 text-cyan-400 border-cyan-800/40",
    swing_breakout: "bg-indigo-900/30 text-indigo-400 border-indigo-800/40",
    swing_pullback: "bg-purple-900/30 text-purple-400 border-purple-800/40",
    macro_inverted: "bg-yellow-900/30 text-yellow-400 border-yellow-800/40",
  };
  const cls = colors[type] ?? "bg-gray-700/30 text-gray-400 border-gray-600/40";
  const label = RULE_META[type]?.label ?? type.replace(/_/g, " ");
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${cls}`} title={RULE_META[type]?.desc}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Create Rule Form
// ---------------------------------------------------------------------------
function CreateRuleForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [ruleType, setRuleType] = useState("price_above");
  const [symbol, setSymbol] = useState("");
  const [threshold, setThreshold] = useState("");
  const [cooldown, setCooldown] = useState("24");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-sm px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors"
      >
        + Buat Rule
      </button>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const body: AlertRuleCreateRequest = {
        rule_type: ruleType,
        canonical_symbol: NEEDS_SYMBOL.has(ruleType) ? symbol.toUpperCase() : undefined,
        threshold_value: NEEDS_THRESHOLD.has(ruleType) && threshold ? parseFloat(threshold) : undefined,
        cooldown_hours: parseInt(cooldown, 10),
        webhook_url: webhookUrl || undefined,
      };
      await api.alerts.createRule(body);
      setOpen(false);
      setSymbol(""); setThreshold(""); setWebhookUrl("");
      onCreated();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Gagal membuat rule");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="bg-gray-900 border border-gray-700 rounded-xl p-4 mb-4">
      <h3 className="text-sm font-semibold mb-3">Buat Alert Rule</h3>
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className="text-xs text-gray-500 mb-1 block">Jenis Alert</label>
          <select
            className="w-full bg-gray-800 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100"
            value={ruleType}
            onChange={e => setRuleType(e.target.value)}
          >
            {RULE_TYPES.map(t => (
              <option key={t} value={t}>{RULE_META[t]?.label ?? t.replace(/_/g, " ")}</option>
            ))}
          </select>
          {RULE_META[ruleType]?.desc && (
            <p className="text-xs text-gray-600 mt-1">{RULE_META[ruleType].desc}</p>
          )}
        </div>

        {NEEDS_SYMBOL.has(ruleType) && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Kode Saham</label>
            <input
              className="w-full bg-gray-800 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100 uppercase"
              placeholder="mis. BBCA"
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              required
            />
          </div>
        )}

        {NEEDS_THRESHOLD.has(ruleType) && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">
              {RULE_META[ruleType]?.thresholdLabel ?? "Nilai Ambang"}
            </label>
            <input
              type="number"
              className="w-full bg-gray-800 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100"
              placeholder={RULE_META[ruleType]?.thresholdPlaceholder ?? "nilai"}
              value={threshold}
              onChange={e => setThreshold(e.target.value)}
              required
            />
          </div>
        )}

        <div>
          <label className="text-xs text-gray-500 mb-1 block">Cooldown (jam)</label>
          <input
            type="number"
            min={1}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100"
            value={cooldown}
            onChange={e => setCooldown(e.target.value)}
          />
        </div>

        <div className="col-span-2">
          <label className="text-xs text-gray-500 mb-1 block">Webhook URL (opsional)</label>
          <input
            type="url"
            className="w-full bg-gray-800 border border-gray-700 rounded px-2.5 py-1.5 text-sm text-gray-100"
            placeholder="https://hooks.slack.com/..."
            value={webhookUrl}
            onChange={e => setWebhookUrl(e.target.value)}
          />
        </div>
      </div>

      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}

      <div className="flex gap-2 mt-3">
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm rounded transition-colors"
        >
          {loading ? "Menyimpan…" : "Simpan"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm rounded transition-colors"
        >
          Batal
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Rules Table
// ---------------------------------------------------------------------------
function RulesTab({ rules, onDelete }: { rules: AlertRuleResponse[]; onDelete: (id: string) => void }) {
  if (rules.length === 0) {
    return <p className="text-sm text-gray-600 py-6 text-center">Belum ada alert rule.</p>;
  }
  return (
    <div className="space-y-2">
      {rules.map(r => (
        <div key={r.id} className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <RuleTypeBadge type={r.rule_type} />
              {r.canonical_symbol && (
                <span className="text-sm font-mono font-semibold text-gray-100">{r.canonical_symbol}</span>
              )}
              {r.threshold_value != null && (
                <span className="text-xs text-gray-400 font-mono">@ {r.threshold_value.toLocaleString()}</span>
              )}
            </div>
            <div className="mt-1 flex gap-3 text-xs text-gray-600 flex-wrap">
              <span>Cooldown: {r.cooldown_hours}j</span>
              <span>Fired: {r.fire_count}×</span>
              {r.last_fired_at && <span>Terakhir: {fmtDatetime(r.last_fired_at)}</span>}
              {r.webhook_url && <span className="text-indigo-500">webhook ✓</span>}
            </div>
          </div>
          <button
            onClick={() => onDelete(r.id)}
            className="text-gray-700 hover:text-red-400 text-xs mt-0.5 shrink-0"
          >
            Hapus
          </button>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// History Tab
// ---------------------------------------------------------------------------
function HistoryTab({ items }: { items: AlertHistoryItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-gray-600 py-6 text-center">Belum ada alert yang terpicu.</p>;
  }
  return (
    <div className="space-y-2">
      {items.map(a => (
        <div key={a.id} className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3">
          <div className="flex items-center justify-between">
            <RuleTypeBadge type={a.event_type} />
            <span className="text-xs text-gray-600">{fmtDatetime(a.created_at)}</span>
          </div>
          {a.payload && (
            <p className="text-sm text-gray-300 mt-1">
              {(a.payload as { message?: string }).message ?? JSON.stringify(a.payload)}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function AlertsPage() {
  const [tab, setTab] = useState<"rules" | "history">("rules");
  const [rules, setRules] = useState<AlertRuleResponse[]>([]);
  const [history, setHistory] = useState<AlertHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [evalResult, setEvalResult] = useState<AlertEvalResponse | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  async function loadRules() {
    setLoading(true);
    try {
      const r = await api.alerts.listRules(false);
      setRules(r);
    } finally {
      setLoading(false);
    }
  }

  async function loadHistory() {
    const h = await api.alerts.history();
    setHistory(h);
  }

  useEffect(() => {
    loadRules();
    loadHistory();
  }, []);

  async function handleDelete(id: string) {
    await api.alerts.deleteRule(id);
    loadRules();
  }

  async function handleEvaluate() {
    setEvaluating(true);
    setEvalResult(null);
    try {
      const r = await api.alerts.evaluate();
      setEvalResult(r);
      loadHistory();
    } finally {
      setEvaluating(false);
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Alert Rules</h1>
          <p className="text-xs text-gray-500 mt-0.5">Monitor harga, RSI, swing, dan macro</p>
        </div>
        <button
          onClick={handleEvaluate}
          disabled={evaluating}
          className="text-sm px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          {evaluating ? "Mengevaluasi…" : "⚡ Evaluasi Sekarang"}
        </button>
      </div>

      {evalResult && (
        <div className="bg-amber-900/20 border border-amber-800/40 rounded-lg px-4 py-3 mb-4 text-sm">
          <span className="text-amber-300 font-medium">
            {evalResult.alerts_fired} alert terpicu
          </span>
          <span className="text-gray-400"> dari {evalResult.rules_checked} rules</span>
          {evalResult.alerts_skipped_cooldown > 0 && (
            <span className="text-gray-600"> · {evalResult.alerts_skipped_cooldown} di-skip (cooldown)</span>
          )}
        </div>
      )}

      <CreateRuleForm onCreated={loadRules} />

      <div className="flex gap-1 mb-4">
        {(["rules", "history"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-sm rounded transition-colors ${
              tab === t ? "bg-gray-800 text-white" : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {t === "rules" ? "Rules" : "History"}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <div key={i} className="h-14 bg-gray-800 rounded-lg animate-pulse" />)}
        </div>
      ) : tab === "rules" ? (
        <RulesTab rules={rules} onDelete={handleDelete} />
      ) : (
        <HistoryTab items={history} />
      )}
    </div>
  );
}
