"use client";

import React, { useEffect, useState } from "react";
import {
  api,
  type MacroSnapshot,
  type PolicyEventList,
  type PolicyEvent,
  type PolicyEventCreateRequest,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmt(value: number | null, unit?: string): string {
  if (value == null) return "—";
  const s = value % 1 === 0 ? value.toFixed(0) : value.toFixed(2);
  return unit ? `${s} ${unit}` : s;
}

function fmtDate(d: string | null): string {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
}

const MATERIALITY_COLORS: Record<string, string> = {
  HIGH:   "bg-red-900/30 text-red-400 border-red-800/40",
  MEDIUM: "bg-amber-900/30 text-amber-400 border-amber-800/40",
  LOW:    "bg-gray-700/30 text-gray-400 border-gray-600/40",
};

function Badge({ label, color }: { label: string; color?: string }) {
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${color ?? "bg-gray-700/30 text-gray-400 border-gray-600/40"}`}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Macro Snapshot tab
// ---------------------------------------------------------------------------
function MacroSnapshotTab() {
  const [data, setData] = useState<MacroSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.macro.snapshot()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-20 bg-gray-800 rounded-lg animate-pulse" />
      ))}
    </div>
  );

  if (error) return (
    <div className="mt-4 rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">{error}</div>
  );

  if (!data || data.observations.length === 0) return (
    <div className="mt-8 text-center text-gray-600 text-sm">Belum ada data makro — import data terlebih dahulu.</div>
  );

  return (
    <div className="mt-4 space-y-4">
      <p className="text-xs text-gray-500">Per {fmtDate(data.as_of)} · {data.total_series} seri</p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {data.observations.map(obs => (
          <div key={obs.series_id} className="bg-gray-800/40 border border-gray-700/40 rounded-lg p-3 space-y-0.5">
            <p className="text-[10px] text-gray-500 uppercase tracking-wide">{obs.label}</p>
            <p className="text-xl font-bold text-gray-100">{fmt(obs.value)}</p>
            <p className="text-[10px] text-gray-600">{fmtDate(obs.observed_date)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add event form
// ---------------------------------------------------------------------------
const MATERIALITY_OPTIONS = ["LOW", "MEDIUM", "HIGH"];
const POLICY_STAGE_OPTIONS = ["DRAFT", "ENACTED", "EFFECTIVE", "REVERSED"];

function AddEventForm({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<PolicyEventCreateRequest>({
    event_type: "MONETARY_POLICY",
    title: "",
    materiality: "MEDIUM",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim()) { setErr("Judul wajib diisi"); return; }
    setSaving(true);
    setErr(null);
    try {
      await api.macro.createEvent(form);
      setOpen(false);
      setForm({ event_type: "MONETARY_POLICY", title: "", materiality: "MEDIUM" });
      onAdded();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Gagal menyimpan");
    } finally {
      setSaving(false);
    }
  }

  if (!open) return (
    <button
      onClick={() => setOpen(true)}
      className="text-xs px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg transition-colors"
    >
      + Tambah Event
    </button>
  );

  return (
    <form onSubmit={submit} className="bg-gray-800/40 border border-gray-700/40 rounded-xl p-4 space-y-3 text-sm">
      <p className="text-xs font-medium text-gray-300">Event Kebijakan Baru</p>
      {err && <p className="text-xs text-red-400">{err}</p>}
      <input
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-gray-500"
        placeholder="Judul event *"
        value={form.title}
        onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
      />
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Tipe</label>
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-gray-500"
            value={form.event_type}
            onChange={e => setForm(f => ({ ...f, event_type: e.target.value }))}
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Materialitas</label>
          <select
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 focus:outline-none"
            value={form.materiality}
            onChange={e => setForm(f => ({ ...f, materiality: e.target.value }))}
          >
            {MATERIALITY_OPTIONS.map(o => <option key={o}>{o}</option>)}
          </select>
        </div>
      </div>
      <textarea
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-gray-500 h-20 resize-none"
        placeholder="Ringkasan singkat (opsional)"
        value={form.summary ?? ""}
        onChange={e => setForm(f => ({ ...f, summary: e.target.value || undefined }))}
      />
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Negara</label>
          <input
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-gray-500"
            placeholder="ID"
            value={form.country ?? ""}
            onChange={e => setForm(f => ({ ...f, country: e.target.value || undefined }))}
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Tahap Kebijakan</label>
          <select
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 focus:outline-none"
            value={form.policy_stage ?? ""}
            onChange={e => setForm(f => ({ ...f, policy_stage: e.target.value || undefined }))}
          >
            <option value="">—</option>
            {POLICY_STAGE_OPTIONS.map(o => <option key={o}>{o}</option>)}
          </select>
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs px-3 py-1.5 text-gray-500 hover:text-gray-300 transition-colors"
        >
          Batal
        </button>
        <button
          type="submit"
          disabled={saving}
          className="text-xs px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white rounded-lg disabled:opacity-50 transition-colors"
        >
          {saving ? "Menyimpan..." : "Simpan"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Policy Events tab
// ---------------------------------------------------------------------------
function PolicyEventsTab() {
  const [data, setData] = useState<PolicyEventList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  function load() {
    setLoading(true);
    api.macro.events({ limit: 50 })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  if (loading) return (
    <div className="mt-4 space-y-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-16 bg-gray-800 rounded-lg animate-pulse" />
      ))}
    </div>
  );

  if (error) return (
    <div className="mt-4 rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">{error}</div>
  );

  return (
    <div className="mt-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500">{data?.total ?? 0} event</p>
        <AddEventForm onAdded={load} />
      </div>

      {(!data || data.events.length === 0) ? (
        <div className="text-center py-8 text-gray-600 text-sm">Belum ada event kebijakan</div>
      ) : (
        <div className="space-y-2">
          {data.events.map(ev => (
            <EventCard
              key={ev.id}
              event={ev}
              expanded={expanded === ev.id}
              onToggle={() => setExpanded(expanded === ev.id ? null : ev.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EventCard({
  event: ev,
  expanded,
  onToggle,
}: {
  event: PolicyEvent;
  expanded: boolean;
  onToggle: () => void;
}) {
  const matColor = MATERIALITY_COLORS[ev.materiality ?? ""] ?? MATERIALITY_COLORS.LOW;

  return (
    <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl overflow-hidden">
      <button className="w-full text-left px-4 py-3 flex gap-3 items-start" onClick={onToggle}>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 mb-0.5">
            {ev.materiality && <Badge label={ev.materiality} color={matColor} />}
            <Badge label={ev.event_type} />
            {ev.country && <Badge label={ev.country} />}
            {ev.policy_stage && <Badge label={ev.policy_stage} />}
          </div>
          <p className="text-sm font-medium text-gray-100 truncate">{ev.title}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {fmtDate(ev.published_at ?? ev.effective_date)}
            {ev.affected_sectors.length > 0 && ` · ${ev.affected_sectors.join(", ")}`}
          </p>
        </div>
        <span className="text-gray-600 text-xs mt-0.5">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-700/30">
          {ev.summary && (
            <p className="text-sm text-gray-300 pt-3">{ev.summary}</p>
          )}
          {ev.company_impacts.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2">Dampak Perusahaan</p>
              <div className="space-y-1">
                {ev.company_impacts.map((imp, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className={`font-medium ${imp.sign === "POSITIVE" ? "text-emerald-400" : imp.sign === "NEGATIVE" ? "text-red-400" : "text-gray-400"}`}>
                      {imp.sign === "POSITIVE" ? "▲" : imp.sign === "NEGATIVE" ? "▼" : "—"}
                    </span>
                    <span className="font-mono text-gray-300">{imp.canonical_symbol}</span>
                    {imp.company_name && <span className="text-gray-500">{imp.company_name}</span>}
                    {imp.mechanism && <span className="text-gray-600">· {imp.mechanism}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
const TABS = ["Indikator Makro", "Event & Kebijakan"] as const;
type Tab = typeof TABS[number];

export default function MacroPage() {
  const [tab, setTab] = useState<Tab>("Indikator Makro");

  return (
    <div className="p-6 space-y-4 max-w-3xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Makroekonomi & Kebijakan</h1>
        <p className="text-xs text-gray-500 mt-0.5">Indikator makro terkini dan event kebijakan yang relevan</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-800">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
              tab === t
                ? "border-blue-500 text-gray-100"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Indikator Makro" && <MacroSnapshotTab />}
      {tab === "Event & Kebijakan" && <PolicyEventsTab />}
    </div>
  );
}
