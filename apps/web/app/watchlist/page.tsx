"use client";

import React, { useEffect, useState } from "react";
import {
  api,
  type WatchlistResponse,
  type WatchlistItemResponse,
  type WatchlistItemAddRequest,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmt(v: number | null, digits = 2): string {
  if (v == null) return "—";
  return v.toLocaleString("id-ID", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function pctColor(v: number | null): string {
  if (v == null) return "text-gray-400";
  if (v > 0) return "text-emerald-400";
  if (v < 0) return "text-red-400";
  return "text-gray-400";
}

function PctBadge({ v, label }: { v: number | null; label: string }) {
  if (v == null) return <span className="text-gray-600 text-xs">—</span>;
  return (
    <span className={`text-xs font-mono ${pctColor(v)}`}>
      {label}: {v > 0 ? "+" : ""}{v.toFixed(2)}%
    </span>
  );
}

function TargetBar({ pct }: { pct: number | null }) {
  if (pct == null || pct < 0) return null;
  const fill = Math.min(100, 100 - pct);
  return (
    <div className="h-1 bg-gray-700 rounded-full mt-1 w-full">
      <div
        className="h-1 bg-emerald-500 rounded-full transition-all"
        style={{ width: `${fill}%` }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Item Modal
// ---------------------------------------------------------------------------
function AddItemModal({
  watchlistId,
  onClose,
  onAdded,
}: {
  watchlistId: string;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [symbol, setSymbol] = useState("");
  const [target, setTarget] = useState("");
  const [cost, setCost] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!symbol.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const body: WatchlistItemAddRequest = {
        canonical_symbol: symbol.trim().toUpperCase(),
        notes: notes || undefined,
        price_target: target ? parseFloat(target) : undefined,
        cost_basis: cost ? parseFloat(cost) : undefined,
        alert_on_target: !!target,
      };
      await api.watchlists.addItem(watchlistId, body);
      onAdded();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Gagal menambah item");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-5 w-full max-w-sm">
        <h3 className="text-sm font-semibold mb-4">Tambah Instrumen</h3>
        <form onSubmit={submit} className="space-y-3">
          <input
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-100 placeholder-gray-500 uppercase"
            placeholder="Symbol (mis. BBCA, AAPL)"
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            required
          />
          <input
            type="number"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-100 placeholder-gray-500"
            placeholder="Price Target (opsional)"
            value={target}
            onChange={e => setTarget(e.target.value)}
          />
          <input
            type="number"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-100 placeholder-gray-500"
            placeholder="Cost Basis (opsional)"
            value={cost}
            onChange={e => setCost(e.target.value)}
          />
          <textarea
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-100 placeholder-gray-500 resize-none"
            placeholder="Catatan (opsional)"
            rows={2}
            value={notes}
            onChange={e => setNotes(e.target.value)}
          />
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm py-2 rounded-lg transition-colors"
            >
              {loading ? "Menyimpan…" : "Tambah"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex-1 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm py-2 rounded-lg transition-colors"
            >
              Batal
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Watchlist Card
// ---------------------------------------------------------------------------
function WatchlistCard({
  wl,
  onRefresh,
}: {
  wl: WatchlistResponse;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<WatchlistResponse | null>(null);
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(false);

  async function loadDetail() {
    if (detail) { setExpanded(e => !e); return; }
    setLoading(true);
    try {
      const d = await api.watchlists.get(wl.id);
      setDetail(d);
      setExpanded(true);
    } finally {
      setLoading(false);
    }
  }

  async function removeItem(itemId: string) {
    await api.watchlists.removeItem(wl.id, itemId);
    const d = await api.watchlists.get(wl.id);
    setDetail(d);
  }

  async function deleteWatchlist() {
    if (!confirm(`Hapus watchlist "${wl.name}"?`)) return;
    await api.watchlists.delete(wl.id);
    onRefresh();
  }

  const items = detail?.items ?? [];

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3">
        <button onClick={loadDetail} className="flex-1 text-left">
          <span className="text-sm font-medium text-gray-100">{wl.name}</span>
          {wl.description && (
            <span className="ml-2 text-xs text-gray-500">{wl.description}</span>
          )}
          <span className="ml-2 text-xs text-gray-600">{wl.item_count} item</span>
        </button>
        <div className="flex gap-2">
          <button
            onClick={() => setAdding(true)}
            className="text-xs px-2.5 py-1 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 rounded border border-indigo-700/40 transition-colors"
          >
            + Tambah
          </button>
          <button
            onClick={deleteWatchlist}
            className="text-xs px-2.5 py-1 bg-red-900/20 hover:bg-red-900/40 text-red-400 rounded border border-red-800/30 transition-colors"
          >
            Hapus
          </button>
        </div>
      </div>

      {loading && (
        <div className="px-4 pb-3">
          <div className="h-10 bg-gray-800 rounded animate-pulse" />
        </div>
      )}

      {expanded && items.length === 0 && !loading && (
        <div className="px-4 pb-4">
          <p className="text-xs text-gray-600 mb-2">Belum ada saham di watchlist ini.</p>
          <p className="text-xs text-gray-700">Klik <span className="text-indigo-400">+ Tambah Saham</span> di atas untuk mulai memantau harga saham favoritmu.</p>
        </div>
      )}

      {expanded && items.length > 0 && (
        <div className="divide-y divide-gray-800">
          {items.map(item => (
            <div key={item.id} className="px-4 py-3 flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-mono font-semibold text-gray-100">{item.canonical_symbol}</span>
                  {item.exchange && (
                    <span className="text-[10px] text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">{item.exchange}</span>
                  )}
                  {item.company_name && (
                    <span className="text-xs text-gray-500 truncate max-w-[140px]">{item.company_name}</span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap gap-3 items-center">
                  <span className="text-xs text-gray-400 font-mono">
                    Harga: {item.last_price != null ? fmt(item.last_price, 0) : "—"}
                  </span>
                  {item.price_target != null && (
                    <span className="text-xs text-gray-400 font-mono">
                      Target: {fmt(item.price_target, 0)}
                    </span>
                  )}
                  <PctBadge v={item.pct_to_target} label="→ Target" />
                  <PctBadge v={item.pct_from_cost} label="dari Beli" />
                </div>
                {item.price_target != null && (
                  <TargetBar pct={item.pct_to_target} />
                )}
                {item.notes && (
                  <p className="text-xs text-gray-600 mt-1 italic">{item.notes}</p>
                )}
              </div>
              <button
                onClick={() => removeItem(item.id)}
                className="text-gray-700 hover:text-red-400 text-xs mt-0.5 shrink-0"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {adding && (
        <AddItemModal
          watchlistId={wl.id}
          onClose={() => setAdding(false)}
          onAdded={async () => {
            const d = await api.watchlists.get(wl.id);
            setDetail(d);
            setExpanded(true);
            onRefresh();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function WatchlistPage() {
  const [watchlists, setWatchlists] = useState<WatchlistResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  async function load() {
    setLoading(true);
    try {
      const data = await api.watchlists.list();
      setWatchlists(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function createWatchlist(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    await api.watchlists.create({ name: newName.trim(), description: newDesc || undefined });
    setNewName("");
    setNewDesc("");
    setCreating(false);
    load();
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Watchlist</h1>
          <p className="text-xs text-gray-500 mt-0.5">Pantau instrumen & price target</p>
        </div>
        <button
          onClick={() => setCreating(c => !c)}
          className="text-sm px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors"
        >
          + Buat Watchlist
        </button>
      </div>

      {creating && (
        <form onSubmit={createWatchlist} className="bg-gray-900 border border-gray-700 rounded-xl p-4 mb-4 flex gap-2">
          <input
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500"
            placeholder="Nama watchlist"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            required
            autoFocus
          />
          <input
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500"
            placeholder="Deskripsi (opsional)"
            value={newDesc}
            onChange={e => setNewDesc(e.target.value)}
          />
          <button type="submit" className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded transition-colors">
            Simpan
          </button>
        </form>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2].map(i => <div key={i} className="h-14 bg-gray-800 rounded-xl animate-pulse" />)}
        </div>
      ) : watchlists.length === 0 ? (
        <div className="text-center py-16 space-y-3">
          <p className="text-gray-400 text-sm font-medium">Belum ada watchlist</p>
          <p className="text-gray-600 text-xs max-w-xs mx-auto leading-relaxed">
            Watchlist membantu kamu memantau harga dan price target saham yang kamu incar.
          </p>
          <button
            onClick={() => setCreating(true)}
            className="mt-2 inline-flex items-center gap-1.5 text-sm px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors"
          >
            + Buat Watchlist Pertama
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {watchlists.map(wl => (
            <WatchlistCard key={wl.id} wl={wl} onRefresh={load} />
          ))}
        </div>
      )}
    </div>
  );
}
