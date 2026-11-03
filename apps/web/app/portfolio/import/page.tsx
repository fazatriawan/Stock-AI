"use client";

import { useRef, useState } from "react";
import { api, type ImportPreviewResponse, type ParsedTradePreview } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Upload, FileText, CheckCircle, AlertTriangle, XCircle, RefreshCw } from "lucide-react";

type Step = "upload" | "preview" | "done";

const BROKER_OPTIONS = [
  { value: "", label: "Auto-detect" },
  { value: "STOCKBIT", label: "Stockbit" },
  { value: "BNI_SEKURITAS", label: "BNI Sekuritas" },
  { value: "MIRAE", label: "Mirae Asset" },
  { value: "IPOT", label: "Indo Premier (IPOT)" },
];

function StatusBadge({ status }: { status: string }) {
  if (status === "OK") return <Badge variant="success">OK</Badge>;
  if (status === "WARNING") return <Badge variant="warning">Peringatan</Badge>;
  return <Badge variant="danger">Error</Badge>;
}

function SummaryStats({ preview }: { preview: ImportPreviewResponse }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div className="bg-gray-800/60 rounded-lg p-3 text-center">
        <p className="text-xs text-gray-500">Total Baris</p>
        <p className="text-lg font-semibold text-gray-100">{preview.total_rows}</p>
      </div>
      <div className="bg-emerald-900/30 rounded-lg p-3 text-center">
        <p className="text-xs text-gray-500">Siap Diimport</p>
        <p className="text-lg font-semibold text-emerald-400">{preview.valid_count}</p>
      </div>
      <div className="bg-amber-900/30 rounded-lg p-3 text-center">
        <p className="text-xs text-gray-500">Duplikat</p>
        <p className="text-lg font-semibold text-amber-400">{preview.duplicate_count}</p>
      </div>
      <div className="bg-red-900/30 rounded-lg p-3 text-center">
        <p className="text-xs text-gray-500">Error</p>
        <p className="text-lg font-semibold text-red-400">{preview.error_count}</p>
      </div>
    </div>
  );
}

export default function ImportPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<Step>("upload");
  const [broker, setBroker] = useState("");
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmResult, setConfirmResult] = useState<{ created: number; skipped: number } | null>(null);

  async function handleFile(file: File) {
    setError(null);
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("broker", broker);
      const result = await api.portfolio.importPreview(fd);
      setPreview(result);
      // Pre-select semua non-ERROR (duplikat ditandai WARNING tapi tetap bisa dipilih)
      const sel = new Set(
        result.trades
          .filter((t) => t.status !== "ERROR")
          .map((t) => t.fingerprint || `row-${t.row_number}`)
      );
      setSelected(sel);
      setStep("preview");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal mengurai file");
    } finally {
      setLoading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  function toggleSelect(fp: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(fp)) next.delete(fp);
      else next.add(fp);
      return next;
    });
  }

  function toggleAll(trades: ParsedTradePreview[]) {
    const nonErrors = trades.filter((t) => t.status !== "ERROR").map((t) => t.fingerprint || `row-${t.row_number}`);
    const allSelected = nonErrors.every((fp) => selected.has(fp));
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(nonErrors));
    }
  }

  async function handleConfirm() {
    if (!preview) return;
    const tradesToCommit = preview.trades.filter((t) => {
      const key = t.fingerprint || `row-${t.row_number}`;
      return selected.has(key) && t.status !== "ERROR";
    });
    if (tradesToCommit.length === 0) {
      setError("Pilih minimal satu transaksi untuk diimport");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const result = await api.portfolio.importConfirm(tradesToCommit);
      setConfirmResult({ created: result.created, skipped: result.skipped_duplicates });
      setStep("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal mengimpor transaksi");
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setStep("upload");
    setPreview(null);
    setSelected(new Set());
    setError(null);
    setConfirmResult(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Import Transaksi</h1>
        <p className="text-xs text-gray-500 mt-0.5">Upload CSV/XLSX/PDF dari broker — preview dulu sebelum commit</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-3 text-xs">
        {(["upload", "preview", "done"] as Step[]).map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            {i > 0 && <span className="text-gray-700">→</span>}
            <span className={step === s ? "text-blue-400 font-medium" : step > s ? "text-gray-500 line-through" : "text-gray-600"}>
              {i + 1}. {s === "upload" ? "Upload" : s === "preview" ? "Verifikasi" : "Selesai"}
            </span>
          </div>
        ))}
      </div>

      {/* === STEP 1: UPLOAD === */}
      {step === "upload" && (
        <Card>
          <CardContent className="pt-6 pb-6 space-y-5">
            {/* Broker selector */}
            <div>
              <label className="block text-xs text-gray-400 mb-1.5">Broker (opsional — untuk auto-format)</label>
              <select
                value={broker}
                onChange={(e) => setBroker(e.target.value)}
                className="w-48 bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-gray-500"
              >
                {BROKER_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {/* Dropzone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
                dragging ? "border-blue-500 bg-blue-950/20" : "border-gray-700 hover:border-gray-500 hover:bg-gray-800/30"
              }`}
            >
              <Upload size={28} className="mx-auto text-gray-600 mb-3" />
              <p className="text-sm text-gray-300">Seret & lepas file di sini</p>
              <p className="text-xs text-gray-600 mt-1">atau klik untuk memilih file</p>
              <p className="text-xs text-gray-700 mt-3">CSV, XLSX, PDF · Maks 10 MB</p>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,.xlsx,.xls,.pdf"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>

            {loading && (
              <div className="flex items-center gap-2 text-blue-400 text-sm">
                <RefreshCw size={14} className="animate-spin" />
                Mengurai file...
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 text-red-400 text-sm">
                <XCircle size={14} />
                {error}
              </div>
            )}

            {/* Format guide */}
            <div className="bg-gray-800/40 rounded-lg p-4 text-xs text-gray-500 space-y-1">
              <p className="font-medium text-gray-400 mb-2">Format kolom yang didukung (CSV/XLSX):</p>
              <p><span className="text-gray-300">Tanggal</span> — Tanggal, Date, Tgl</p>
              <p><span className="text-gray-300">Kode</span> — Kode Saham, Symbol, Ticker, Kode</p>
              <p><span className="text-gray-300">Jenis</span> — Jenis, Aksi, Side, Type (Beli/Buy/Jual/Sell)</p>
              <p><span className="text-gray-300">Lot</span> — Lot, Lots, Volume (Lot)</p>
              <p><span className="text-gray-300">Harga</span> — Harga, Price, Execution Price</p>
              <p><span className="text-gray-300">Fee</span> — Fee, Komisi (opsional)</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* === STEP 2: PREVIEW === */}
      {step === "preview" && preview && (
        <div className="space-y-4">
          <SummaryStats preview={preview} />

          {/* Parse errors */}
          {preview.parse_errors.length > 0 && (
            <div className="rounded border border-red-800/40 bg-red-950/20 px-4 py-3 space-y-1">
              <p className="text-xs font-medium text-red-400">Error saat parsing:</p>
              {preview.parse_errors.map((e, i) => (
                <p key={i} className="text-xs text-red-300/70">{e}</p>
              ))}
            </div>
          )}

          {/* Global warnings */}
          {preview.warnings.length > 0 && (
            <div className="rounded border border-amber-800/40 bg-amber-950/20 px-4 py-3 space-y-1">
              {preview.warnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-300/70">⚠ {w}</p>
              ))}
            </div>
          )}

          <p className="text-xs text-gray-500">
            Format terdeteksi: <span className="text-gray-300">{preview.broker_format}</span>
            {" · "}Pilih transaksi yang ingin diimport, lalu klik Konfirmasi.
          </p>

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-800 text-gray-500">
                      <th className="py-2.5 px-3 text-left">
                        <input
                          type="checkbox"
                          checked={preview.trades.filter((t) => t.status !== "ERROR").every(
                            (t) => selected.has(t.fingerprint || `row-${t.row_number}`)
                          )}
                          onChange={() => toggleAll(preview.trades)}
                          className="rounded"
                        />
                      </th>
                      <th className="py-2.5 px-3 text-left">Baris</th>
                      <th className="py-2.5 px-3 text-left">Saham</th>
                      <th className="py-2.5 px-3 text-left">Tanggal</th>
                      <th className="py-2.5 px-3 text-left">Jenis</th>
                      <th className="py-2.5 px-3 text-right">Lot</th>
                      <th className="py-2.5 px-3 text-right">Harga</th>
                      <th className="py-2.5 px-3 text-right">Nilai</th>
                      <th className="py-2.5 px-3 text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.trades.map((t) => {
                      const key = t.fingerprint || `row-${t.row_number}`;
                      const isChecked = selected.has(key);
                      const isError = t.status === "ERROR";
                      return (
                        <tr
                          key={key}
                          className={`border-b border-gray-800/50 ${isError ? "opacity-50" : "hover:bg-gray-800/20"}`}
                        >
                          <td className="py-2 px-3">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              disabled={isError}
                              onChange={() => toggleSelect(key)}
                              className="rounded"
                            />
                          </td>
                          <td className="py-2 px-3 text-gray-600">{t.row_number}</td>
                          <td className="py-2 px-3">
                            <span className="font-medium text-gray-200">
                              {t.canonical_symbol.split(":")[1] ?? t.canonical_symbol}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-gray-400">{t.trade_date}</td>
                          <td className="py-2 px-3">
                            <span className={t.side === "BUY" ? "text-emerald-400" : "text-red-400"}>
                              {t.side}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-right text-gray-300">{t.lots}</td>
                          <td className="py-2 px-3 text-right text-gray-300">{formatCurrency(t.price)}</td>
                          <td className="py-2 px-3 text-right text-gray-400">
                            {formatCurrency(t.shares * t.price)}
                          </td>
                          <td className="py-2 px-3 text-center">
                            <StatusBadge status={t.status} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {error && (
            <div className="flex items-center gap-2 text-red-400 text-sm">
              <XCircle size={14} />
              {error}
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="outline" onClick={reset}>
              Ganti File
            </Button>
            <Button
              onClick={handleConfirm}
              disabled={loading || selected.size === 0}
              className="bg-emerald-700 hover:bg-emerald-600"
            >
              {loading ? "Menyimpan..." : `Konfirmasi ${selected.size} Transaksi`}
            </Button>
          </div>

          <p className="text-xs text-gray-600">
            Keputusan import sepenuhnya menjadi tanggung jawab pengguna.
          </p>
        </div>
      )}

      {/* === STEP 3: DONE === */}
      {step === "done" && confirmResult && (
        <Card>
          <CardContent className="py-12 text-center space-y-4">
            <CheckCircle size={40} className="mx-auto text-emerald-400" />
            <div>
              <p className="text-base font-semibold text-gray-100">
                {confirmResult.created} transaksi berhasil diimport
              </p>
              {confirmResult.skipped > 0 && (
                <p className="text-sm text-gray-500 mt-1">
                  {confirmResult.skipped} duplikat dilewati
                </p>
              )}
            </div>
            <div className="flex justify-center gap-3">
              <Button onClick={reset} variant="outline">Import Lagi</Button>
              <Button onClick={() => window.location.href = "/portfolio"}>
                Lihat Portofolio
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
