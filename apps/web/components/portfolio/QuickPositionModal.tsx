"use client";

import { useState } from "react";
import { api, type QuickPositionRequest } from "@/lib/api";
import { X, AlertTriangle, CheckCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatCurrency } from "@/lib/utils";

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

export function QuickPositionModal({ onClose, onSuccess }: Props) {
  const today = new Date().toISOString().split("T")[0];
  const [symbol, setSymbol] = useState("");
  const [lots, setLots] = useState<string>("");
  const [avgPrice, setAvgPrice] = useState<string>("");
  const [tradeDate, setTradeDate] = useState(today);
  const [fee, setFee] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ symbol: string; lots: number; total: number } | null>(null);

  const lotsNum = parseInt(lots) || 0;
  const priceNum = parseFloat(avgPrice) || 0;
  const feeNum = parseFloat(fee) || 0;
  const totalCost = lotsNum * 100 * priceNum + feeNum;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!symbol.trim()) { setError("Kode saham wajib diisi"); return; }
    if (lotsNum <= 0) { setError("Lot harus > 0"); return; }
    if (priceNum <= 0) { setError("Harga rata-rata harus > 0"); return; }

    setLoading(true);
    setError(null);
    try {
      const req: QuickPositionRequest = {
        symbol: symbol.trim().toUpperCase(),
        lots: lotsNum,
        avg_price: priceNum,
        trade_date: tradeDate || undefined,
        fee: feeNum || undefined,
        notes: notes || undefined,
      };
      const res = await api.portfolio.quickAddPosition(req);
      setSuccess({ symbol: res.canonical_symbol, lots: res.lots, total: res.total_cost });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan posisi");
    } finally {
      setLoading(false);
    }
  }

  if (success) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
        <div className="w-full max-w-sm bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-6 text-center space-y-4">
          <CheckCircle size={36} className="mx-auto text-emerald-400" />
          <div>
            <p className="text-sm font-semibold text-gray-100">
              {success.symbol.split(":")[1] ?? success.symbol} — {success.lots} lot ditambahkan
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Total modal: {formatCurrency(success.total)}
            </p>
            <p className="text-xs text-gray-600 mt-0.5">
              Harga terkini sedang di-refresh di background via yfinance
            </p>
          </div>
          <div className="flex gap-3 justify-center">
            <Button variant="outline" onClick={onClose}>Tutup</Button>
            <Button
              className="bg-emerald-700 hover:bg-emerald-600"
              onClick={() => {
                setSuccess(null);
                setSymbol(""); setLots(""); setAvgPrice(""); setFee(""); setNotes("");
              }}
            >
              Tambah Lagi
            </Button>
          </div>
          <Button variant="outline" className="w-full text-xs" onClick={() => { onSuccess(); onClose(); }}>
            Lihat Portofolio
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md bg-gray-900 border border-gray-700 rounded-xl shadow-2xl p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-sm font-semibold text-gray-100">Tambah Posisi</h2>
            <p className="text-xs text-gray-500 mt-0.5">Input lot + harga rata-rata beli</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Symbol */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Kode Saham IDX</label>
            <input
              type="text"
              placeholder="BBCA / BBRI / BMRI"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500 uppercase"
            />
          </div>

          {/* Lot + Harga */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Lot</label>
              <input
                type="number"
                min="1"
                step="1"
                placeholder="5"
                value={lots}
                onChange={(e) => setLots(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500"
              />
              {lotsNum > 0 && (
                <p className="text-xs text-gray-600 mt-0.5">= {(lotsNum * 100).toLocaleString("id-ID")} saham</p>
              )}
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Harga Rata-rata (Rp)</label>
              <input
                type="number"
                min="1"
                step="1"
                placeholder="5000"
                value={avgPrice}
                onChange={(e) => setAvgPrice(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500"
              />
            </div>
          </div>

          {/* Total preview */}
          {lotsNum > 0 && priceNum > 0 && (
            <div className="bg-gray-800/60 rounded-md px-3 py-2 text-xs text-gray-400">
              Modal: {formatCurrency(totalCost)}
              <span className="text-gray-600 ml-2">({lotsNum} lot × 100 × {formatCurrency(priceNum)})</span>
            </div>
          )}

          {/* Tanggal + Fee */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Tanggal Beli</label>
              <input
                type="date"
                value={tradeDate}
                onChange={(e) => setTradeDate(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-gray-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Fee Broker (Rp)</label>
              <input
                type="number"
                min="0"
                placeholder="0"
                value={fee}
                onChange={(e) => setFee(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:outline-none focus:border-gray-500"
              />
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Catatan (opsional)</label>
            <input
              type="text"
              placeholder="Misal: beli bertahap 2024"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
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
              className="flex-1 bg-emerald-700 hover:bg-emerald-600"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <RefreshCw size={13} className="animate-spin" />
                  Menyimpan...
                </span>
              ) : "Tambah Posisi"}
            </Button>
          </div>

          <p className="text-xs text-gray-600 text-center">
            Harga akan diperbarui otomatis via yfinance setelah disimpan.
            Keputusan input sepenuhnya tanggung jawab pengguna.
          </p>
        </form>
      </div>
    </div>
  );
}
