"use client";

import { useState } from "react";
import { api, type Position } from "@/lib/api";
import { X, AlertTriangle, CheckCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatCurrency } from "@/lib/utils";

interface Props {
  position: Position;
  onClose: () => void;
  onSuccess: () => void;
}

export function EditPositionModal({ position, onClose, onSuccess }: Props) {
  const ticker = position.canonical_symbol.split(":")[1] ?? position.canonical_symbol;
  const today = new Date().toISOString().split("T")[0];

  const [lots, setLots] = useState<string>(String(Math.round(position.lots)));
  const [avgPrice, setAvgPrice] = useState<string>(String(position.avg_cost));
  const [tradeDate, setTradeDate] = useState(today);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const lotsNum = parseInt(lots) || 0;
  const priceNum = parseFloat(avgPrice) || 0;
  const totalCost = lotsNum * 100 * priceNum;

  const lotsChanged = lotsNum !== Math.round(position.lots);
  const priceChanged = Math.abs(priceNum - position.avg_cost) > 0.01;
  const hasChange = lotsChanged || priceChanged;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (lotsNum <= 0) { setError("Lot harus > 0"); return; }
    if (priceNum <= 0) { setError("Harga rata-rata harus > 0"); return; }

    setLoading(true);
    setError(null);
    try {
      await api.portfolio.editPosition(position.canonical_symbol, {
        lots: lotsNum,
        avg_price: priceNum,
        trade_date: tradeDate || undefined,
        notes: notes || undefined,
      });
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan perubahan");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div>
            <h2 className="text-sm font-semibold text-gray-100">Edit Posisi — {ticker}</h2>
            {position.company_name && (
              <p className="text-xs text-gray-500 mt-0.5">{position.company_name}</p>
            )}
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <X size={16} />
          </button>
        </div>

        {done ? (
          <div className="px-5 py-10 text-center space-y-3">
            <CheckCircle size={32} className="text-emerald-400 mx-auto" />
            <p className="text-sm font-medium text-gray-100">Posisi berhasil diperbarui</p>
            <p className="text-xs text-gray-500">
              {ticker}: {lotsNum} lot @ {formatCurrency(priceNum)}
            </p>
            <Button size="sm" onClick={onSuccess} className="mt-2">
              Tutup
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="px-5 py-5 space-y-4">
            {/* Info sekarang */}
            <div className="bg-gray-800/40 rounded-xl px-4 py-3 text-xs text-gray-500 space-y-1">
              <p className="text-gray-400 font-medium mb-1.5">Posisi saat ini</p>
              <div className="flex justify-between">
                <span>Lot / Saham</span>
                <span className="text-gray-300">{Math.round(position.lots)} lot ({position.shares.toLocaleString("id-ID")} saham)</span>
              </div>
              <div className="flex justify-between">
                <span>Harga Rata-rata</span>
                <span className="text-gray-300">{formatCurrency(position.avg_cost)}</span>
              </div>
              <div className="flex justify-between">
                <span>Total Modal</span>
                <span className="text-gray-300">{formatCurrency(position.avg_cost * position.shares)}</span>
              </div>
            </div>

            {/* Form input */}
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1.5">Jumlah Lot Baru</label>
                <input
                  type="number"
                  min="1"
                  value={lots}
                  onChange={e => setLots(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
                  placeholder="Contoh: 10"
                  required
                />
                {lotsNum > 0 && (
                  <p className="text-xs text-gray-600 mt-1">{lotsNum} lot = {(lotsNum * 100).toLocaleString("id-ID")} saham</p>
                )}
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1.5">Harga Rata-rata Baru (Rp/saham)</label>
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  value={avgPrice}
                  onChange={e => setAvgPrice(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
                  placeholder="Contoh: 4200"
                  required
                />
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1.5">Tanggal Beli</label>
                <input
                  type="date"
                  value={tradeDate}
                  onChange={e => setTradeDate(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1.5">Catatan (opsional)</label>
                <input
                  type="text"
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500"
                  placeholder="Alasan koreksi..."
                />
              </div>
            </div>

            {/* Preview total */}
            {lotsNum > 0 && priceNum > 0 && (
              <div className="bg-gray-800/40 rounded-xl px-4 py-3 text-xs space-y-1">
                <p className="text-gray-400 font-medium mb-1.5">Setelah diperbarui</p>
                <div className="flex justify-between">
                  <span className="text-gray-500">Total Modal</span>
                  <span className={`font-medium ${hasChange ? "text-blue-300" : "text-gray-300"}`}>
                    {formatCurrency(totalCost)}
                  </span>
                </div>
                {lotsChanged && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Lot berubah</span>
                    <span className="text-amber-400">{Math.round(position.lots)} → {lotsNum} lot</span>
                  </div>
                )}
                {priceChanged && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Harga berubah</span>
                    <span className="text-amber-400">{formatCurrency(position.avg_cost)} → {formatCurrency(priceNum)}</span>
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 text-xs text-red-400 bg-red-950/20 rounded-lg px-3 py-2">
                <AlertTriangle size={12} />
                {error}
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <Button type="button" variant="outline" size="sm" onClick={onClose} className="flex-1">
                Batal
              </Button>
              <Button type="submit" size="sm" disabled={loading || !hasChange} className="flex-1">
                {loading ? <><RefreshCw size={12} className="animate-spin mr-1" /> Menyimpan...</> : "Simpan Perubahan"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
