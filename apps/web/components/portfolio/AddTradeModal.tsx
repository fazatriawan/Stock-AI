"use client";

import { useState } from "react";
import { api, type TradeCreateRequest } from "@/lib/api";
import { X, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

export function AddTradeModal({ onClose, onSuccess }: Props) {
  const today = new Date().toISOString().split("T")[0];

  const [form, setForm] = useState<TradeCreateRequest>({
    canonical_symbol: "",
    trade_date: today,
    side: "BUY",
    shares: 0,
    price: 0,
    fee: 0,
    tax: 0,
    notes: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof TradeCreateRequest>(key: K, value: TradeCreateRequest[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.canonical_symbol.trim()) {
      setError("Kode saham wajib diisi");
      return;
    }
    if (form.shares <= 0) {
      setError("Saham harus lebih dari 0");
      return;
    }
    if (form.price <= 0) {
      setError("Harga harus lebih dari 0");
      return;
    }

    try {
      setLoading(true);
      setError(null);
      // Normalise symbol: "BMRI" → "IDX:BMRI"
      const symbol = form.canonical_symbol.includes(":")
        ? form.canonical_symbol.toUpperCase()
        : `IDX:${form.canonical_symbol.toUpperCase()}`;
      await api.portfolio.addTrade({ ...form, canonical_symbol: symbol });
      onSuccess();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menambah trade");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-semibold text-gray-100">Tambah Transaksi Manual</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Symbol */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Kode Saham</label>
            <input
              type="text"
              placeholder="BMRI atau IDX:BMRI"
              value={form.canonical_symbol}
              onChange={(e) => update("canonical_symbol", e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500"
            />
          </div>

          {/* Side + Date */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Jenis</label>
              <select
                value={form.side}
                onChange={(e) => update("side", e.target.value as "BUY" | "SELL")}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-gray-500"
              >
                <option value="BUY">BUY — Beli</option>
                <option value="SELL">SELL — Jual</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Tanggal</label>
              <input
                type="date"
                value={form.trade_date}
                onChange={(e) => update("trade_date", e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-gray-500"
              />
            </div>
          </div>

          {/* Shares + Price */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Saham (bukan lot)</label>
              <input
                type="number"
                min="100"
                step="100"
                placeholder="100"
                value={form.shares || ""}
                onChange={(e) => update("shares", parseFloat(e.target.value) || 0)}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500"
              />
              {form.shares > 0 && (
                <p className="text-xs text-gray-600 mt-0.5">= {(form.shares / 100).toFixed(0)} lot</p>
              )}
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Harga (Rp/saham)</label>
              <input
                type="number"
                min="1"
                step="1"
                placeholder="5000"
                value={form.price || ""}
                onChange={(e) => update("price", parseFloat(e.target.value) || 0)}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500"
              />
            </div>
          </div>

          {/* Fee + Tax */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Fee (Rp)</label>
              <input
                type="number"
                min="0"
                value={form.fee || ""}
                onChange={(e) => update("fee", parseFloat(e.target.value) || 0)}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Pajak (Rp)</label>
              <input
                type="number"
                min="0"
                value={form.tax || ""}
                onChange={(e) => update("tax", parseFloat(e.target.value) || 0)}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500"
              />
            </div>
          </div>

          {/* Total preview */}
          {form.shares > 0 && form.price > 0 && (
            <div className="bg-gray-800/60 rounded-md px-3 py-2 text-xs text-gray-400">
              Total: Rp {((form.shares * form.price) + (form.fee || 0) + (form.tax || 0)).toLocaleString("id-ID")}
            </div>
          )}

          {/* Notes */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Catatan (opsional)</label>
            <input
              type="text"
              placeholder="Misal: beli di support SMA50"
              value={form.notes || ""}
              onChange={(e) => update("notes", e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 text-red-400 text-xs">
              <AlertTriangle size={13} />
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <Button type="button" variant="outline" className="flex-1" onClick={onClose}>
              Batal
            </Button>
            <Button
              type="submit"
              disabled={loading}
              className={`flex-1 ${form.side === "BUY" ? "bg-emerald-700 hover:bg-emerald-600" : "bg-red-700 hover:bg-red-600"}`}
            >
              {loading ? "Menyimpan..." : form.side === "BUY" ? "Tambah BUY" : "Tambah SELL"}
            </Button>
          </div>

          <p className="text-xs text-gray-600 text-center">
            Keputusan transaksi sepenuhnya menjadi tanggung jawab pengguna.
          </p>
        </form>
      </div>
    </div>
  );
}
