"use client";

import React, { useEffect, useState } from "react";
import { api, type JournalEntry, type JournalCreateRequest } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Plus, BookOpen, CheckCircle, XCircle, Clock, ChevronDown, ChevronUp } from "lucide-react";

const ACTION_BADGE: Record<string, "success" | "danger" | "warning" | "default"> = {
  BUY: "success",
  SELL: "danger",
  HOLD: "default",
  WATCH: "warning",
};

const OUTCOME_STYLE: Record<string, { color: string; icon: React.ReactElement }> = {
  CORRECT: { color: "text-emerald-400", icon: <CheckCircle size={12} /> },
  INCORRECT: { color: "text-red-400", icon: <XCircle size={12} /> },
  PENDING: { color: "text-gray-500", icon: <Clock size={12} /> },
};

function JournalCard({ entry, onReview }: { entry: JournalEntry; onReview: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [outcome, setOutcome] = useState<"CORRECT" | "INCORRECT" | "PENDING">("PENDING");
  const [outcomeNotes, setOutcomeNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const ticker = entry.canonical_symbol.split(":")[1] ?? entry.canonical_symbol;
  const outcomeStyle = entry.outcome ? OUTCOME_STYLE[entry.outcome] : null;

  async function submitReview() {
    setSaving(true);
    try {
      await api.journal.review(entry.id, outcome, outcomeNotes || undefined);
      setReviewing(false);
      onReview();
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardContent className="py-3 px-4 space-y-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-100">{ticker}</span>
            <Badge variant={ACTION_BADGE[entry.action]}>{entry.action}</Badge>
            {entry.outcome && outcomeStyle && (
              <span className={`flex items-center gap-1 text-xs ${outcomeStyle.color}`}>
                {outcomeStyle.icon}
                {entry.outcome === "CORRECT" ? "Tepat" : entry.outcome === "INCORRECT" ? "Salah" : "Pending"}
              </span>
            )}
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-600">{entry.decision_date}</p>
            {entry.price_at_decision && (
              <p className="text-xs text-gray-600">{formatCurrency(entry.price_at_decision)}</p>
            )}
          </div>
        </div>

        <p className="text-xs text-gray-300">{entry.rationale}</p>

        {(entry.thesis || entry.invalidation) && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-600 hover:text-gray-400 flex items-center gap-1"
          >
            {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            {expanded ? "Sembunyikan detail" : "Lihat tesis & invalidasi"}
          </button>
        )}

        {expanded && (
          <div className="space-y-2 pt-1 border-t border-gray-800/50">
            {entry.thesis && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-0.5">Tesis</p>
                <p className="text-xs text-gray-400">{entry.thesis}</p>
              </div>
            )}
            {entry.invalidation && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-0.5">Kapan keluar?</p>
                <p className="text-xs text-gray-400">{entry.invalidation}</p>
              </div>
            )}
            {entry.outcome_notes && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-0.5">Catatan review</p>
                <p className="text-xs text-gray-400">{entry.outcome_notes}</p>
              </div>
            )}
          </div>
        )}

        {/* Review form */}
        {reviewing ? (
          <div className="space-y-2 pt-2 border-t border-gray-800/50">
            <p className="text-xs text-gray-400">Apakah keputusan ini terbukti tepat?</p>
            <div className="flex gap-2">
              {(["CORRECT", "INCORRECT", "PENDING"] as const).map((o) => (
                <button
                  key={o}
                  onClick={() => setOutcome(o)}
                  className={`px-3 py-1 rounded text-xs transition-colors ${
                    outcome === o
                      ? o === "CORRECT" ? "bg-emerald-900/50 text-emerald-300"
                        : o === "INCORRECT" ? "bg-red-900/50 text-red-300"
                        : "bg-gray-700 text-gray-300"
                      : "text-gray-600 hover:text-gray-400"
                  }`}
                >
                  {o === "CORRECT" ? "Tepat" : o === "INCORRECT" ? "Salah" : "Masih Pending"}
                </button>
              ))}
            </div>
            <textarea
              value={outcomeNotes}
              onChange={(e) => setOutcomeNotes(e.target.value)}
              placeholder="Catatan evaluasi (opsional)..."
              rows={2}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-300 focus:outline-none focus:border-gray-600 resize-none"
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={submitReview} disabled={saving}>
                {saving ? "Menyimpan..." : "Simpan Review"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setReviewing(false)}>Batal</Button>
            </div>
          </div>
        ) : (
          !entry.outcome && (
            <button
              onClick={() => setReviewing(true)}
              className="text-xs text-gray-600 hover:text-blue-400"
            >
              + Review keputusan ini
            </button>
          )
        )}
      </CardContent>
    </Card>
  );
}

function AddEntryModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<JournalCreateRequest>({
    canonical_symbol: "",
    decision_date: new Date().toISOString().split("T")[0],
    action: "BUY",
    rationale: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!form.canonical_symbol || !form.rationale) {
      setError("Kode saham dan alasan wajib diisi");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const sym = form.canonical_symbol.toUpperCase();
      await api.journal.create({
        ...form,
        canonical_symbol: sym.includes(":") ? sym : `IDX:${sym}`,
      });
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md space-y-4 p-6">
        <h2 className="text-sm font-semibold text-gray-100">Tambah Catatan Keputusan</h2>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Kode Saham</label>
            <input
              value={form.canonical_symbol}
              onChange={(e) => setForm(f => ({ ...f, canonical_symbol: e.target.value }))}
              placeholder="BMRI"
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-gray-500"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Tanggal</label>
            <input
              type="date"
              value={form.decision_date}
              onChange={(e) => setForm(f => ({ ...f, decision_date: e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-gray-500"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">Keputusan</label>
          <div className="flex gap-2">
            {(["BUY", "SELL", "HOLD", "WATCH"] as const).map((a) => (
              <button
                key={a}
                onClick={() => setForm(f => ({ ...f, action: a }))}
                className={`px-3 py-1.5 rounded text-xs transition-colors ${
                  form.action === a
                    ? a === "BUY" ? "bg-emerald-900/50 text-emerald-300 border border-emerald-700/40"
                      : a === "SELL" ? "bg-red-900/50 text-red-300 border border-red-700/40"
                      : "bg-gray-700 text-gray-200 border border-gray-600"
                    : "text-gray-600 hover:text-gray-400"
                }`}
              >
                {a}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">Alasan keputusan *</label>
          <textarea
            value={form.rationale}
            onChange={(e) => setForm(f => ({ ...f, rationale: e.target.value }))}
            placeholder="Mengapa kamu membuat keputusan ini?"
            rows={3}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-gray-500 resize-none"
          />
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">Tesis investasi (opsional)</label>
          <textarea
            value={form.thesis ?? ""}
            onChange={(e) => setForm(f => ({ ...f, thesis: e.target.value || undefined }))}
            placeholder="Apa yang kamu harapkan terjadi?"
            rows={2}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-400 focus:outline-none focus:border-gray-500 resize-none"
          />
        </div>

        <div>
          <label className="block text-xs text-gray-500 mb-1">Kapan tesis ini patah? (opsional)</label>
          <input
            value={form.invalidation ?? ""}
            onChange={(e) => setForm(f => ({ ...f, invalidation: e.target.value || undefined }))}
            placeholder="Kondisi yang akan mengubah pandangan saya..."
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-400 focus:outline-none focus:border-gray-500"
          />
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}

        <div className="flex gap-2 pt-1">
          <Button onClick={submit} disabled={saving} className="flex-1">
            {saving ? "Menyimpan..." : "Simpan Catatan"}
          </Button>
          <Button variant="outline" onClick={onClose}>Batal</Button>
        </div>
      </div>
    </div>
  );
}

export default function JournalPage() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [filterAction, setFilterAction] = useState<string>("ALL");

  async function load() {
    setLoading(true);
    try {
      const data = await api.journal.list();
      setEntries(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const filtered = filterAction === "ALL"
    ? entries
    : entries.filter(e => e.action === filterAction);

  const reviewed = entries.filter(e => e.outcome).length;
  const correct = entries.filter(e => e.outcome === "CORRECT").length;
  const accuracy = reviewed > 0 ? Math.round((correct / reviewed) * 100) : null;

  return (
    <div className="p-6 space-y-5 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Decision Journal</h1>
          <p className="text-xs text-gray-500 mt-0.5">Rekam alasan di balik setiap keputusan investasi</p>
        </div>
        <Button onClick={() => setShowModal(true)} size="sm">
          <Plus size={14} className="mr-1" />
          Tambah Catatan
        </Button>
      </div>

      {/* Stats */}
      {entries.length > 0 && (
        <div className="grid grid-cols-3 gap-3 text-xs">
          <div className="bg-gray-800/50 rounded-lg p-3 text-center">
            <p className="text-gray-600">Total Catatan</p>
            <p className="text-xl font-bold text-gray-200">{entries.length}</p>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-3 text-center">
            <p className="text-gray-600">Sudah Direview</p>
            <p className="text-xl font-bold text-gray-200">{reviewed}</p>
          </div>
          <div className={`rounded-lg p-3 text-center ${accuracy !== null ? (accuracy >= 60 ? "bg-emerald-900/20" : "bg-amber-900/20") : "bg-gray-800/50"}`}>
            <p className="text-gray-600">Akurasi</p>
            <p className={`text-xl font-bold ${accuracy !== null ? (accuracy >= 60 ? "text-emerald-400" : "text-amber-400") : "text-gray-600"}`}>
              {accuracy !== null ? `${accuracy}%` : "—"}
            </p>
          </div>
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-2 text-xs">
        {(["ALL", "BUY", "SELL", "HOLD", "WATCH"] as const).map((a) => (
          <button
            key={a}
            onClick={() => setFilterAction(a)}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              filterAction === a ? "bg-gray-700 text-gray-100" : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {a === "ALL" ? `Semua (${entries.length})` : a}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="h-20 bg-gray-800 rounded-lg animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12">
          <BookOpen size={32} className="mx-auto text-gray-700 mb-3" />
          <p className="text-sm text-gray-600">
            {entries.length === 0
              ? "Belum ada catatan — mulai rekam keputusan investasimu"
              : "Tidak ada catatan untuk filter ini"}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(e => (
            <JournalCard key={e.id} entry={e} onReview={load} />
          ))}
        </div>
      )}

      {showModal && (
        <AddEntryModal onClose={() => setShowModal(false)} onSaved={load} />
      )}

      {entries.length > 0 && (
        <p className="text-xs text-gray-700">
          Jurnal membantu meningkatkan disiplin dan akurasi keputusan investasi dari waktu ke waktu.
        </p>
      )}
    </div>
  );
}
