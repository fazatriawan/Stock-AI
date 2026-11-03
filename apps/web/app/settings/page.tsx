"use client";

import React, { useEffect, useState } from "react";
import { api, type DataHealth } from "@/lib/api";
import { CheckCircle, XCircle, AlertCircle, RefreshCw, Database } from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtDate(d: string | null): string {
  if (!d) return "—";
  return new Date(d).toLocaleString("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusIcon({ status }: { status: string }) {
  if (status === "OK") return <CheckCircle size={14} className="text-emerald-400 shrink-0" />;
  if (status === "DEGRADED") return <AlertCircle size={14} className="text-amber-400 shrink-0" />;
  return <XCircle size={14} className="text-red-400 shrink-0" />;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    OK:       "bg-emerald-900/30 text-emerald-400 border-emerald-800/40",
    DEGRADED: "bg-amber-900/30 text-amber-400 border-amber-800/40",
    DOWN:     "bg-red-900/30 text-red-400 border-red-800/40",
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${map[status] ?? "bg-gray-700 text-gray-400 border-gray-600"}`}>
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Data Health section
// ---------------------------------------------------------------------------
function DataHealthSection() {
  const [data, setData] = useState<DataHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api.data.health()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-300">Status Provider Data</h2>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {data && (
        <>
          <p className="text-xs text-gray-600">Dicek pada {fmtDate(data.checked_at)}</p>
          <div className="space-y-1.5">
            {data.providers.length === 0 ? (
              <p className="text-sm text-gray-600">Tidak ada provider terdaftar</p>
            ) : (
              data.providers.map(p => (
                <div
                  key={p.provider}
                  className="bg-gray-800/30 border border-gray-700/40 rounded-lg px-4 py-3 flex items-start gap-3"
                >
                  <StatusIcon status={p.status} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-gray-200">{p.provider}</span>
                      <StatusBadge status={p.status} />
                    </div>
                    {p.last_success && (
                      <p className="text-xs text-gray-500 mt-0.5">Sukses terakhir: {fmtDate(p.last_success)}</p>
                    )}
                    {p.last_error && (
                      <p className="text-xs text-red-400/70 mt-0.5 truncate">{p.last_error}</p>
                    )}
                    {p.notes && (
                      <p className="text-xs text-gray-600 mt-0.5">{p.notes}</p>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bootstrap section
// ---------------------------------------------------------------------------
function BootstrapSection() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ message: string; instruments_loaded: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function bootstrap() {
    if (!confirm("Bootstrap akan memuat data mock/contoh ke database. Lanjutkan?")) return;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const r = await api.admin.bootstrap(true);
      setResult(r);
    } catch (ex) {
      setError(ex instanceof Error ? ex.message : "Gagal bootstrap");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-gray-300">Bootstrap Data</h2>
      <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 space-y-3">
        <div className="flex items-start gap-3">
          <Database size={16} className="text-gray-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm text-gray-200">Load Data Mock</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Muat instrumen, harga historis, dan data fundamental contoh ke database lokal.
              Hanya untuk development — tidak menggunakan data pasar nyata.
            </p>
          </div>
        </div>

        {result && (
          <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 px-3 py-2 text-xs text-emerald-400">
            {result.message} · {result.instruments_loaded} instrumen dimuat
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-3 py-2 text-xs text-red-400">
            {error}
          </div>
        )}

        <button
          onClick={bootstrap}
          disabled={loading}
          className="text-xs px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg disabled:opacity-50 transition-colors"
        >
          {loading ? "Memuat..." : "Jalankan Bootstrap"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// About section
// ---------------------------------------------------------------------------
function AboutSection() {
  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-gray-300">Tentang</h2>
      <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 space-y-2 text-xs text-gray-400">
        <div className="flex justify-between">
          <span className="text-gray-500">Versi</span>
          <span>v1.1.0</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Stack</span>
          <span>Next.js 14 · FastAPI · PostgreSQL</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Pasar</span>
          <span>IDX (Indonesia) · US</span>
        </div>
        <hr className="border-gray-700/40 my-1" />
        <p className="text-gray-600 leading-relaxed">
          Alat riset ekuitas pribadi. Tidak pernah mengeksekusi transaksi atau terhubung ke broker secara
          otomatis. Semua keputusan beli/jual sepenuhnya ada di tangan pengguna.
        </p>
        <p className="text-gray-600 leading-relaxed">
          <strong className="text-gray-500">Bukan nasihat investasi.</strong> Angka yang ditampilkan
          berasal dari provider data pihak ketiga dan mungkin terlambat atau tidak akurat.
          Selalu verifikasi secara independen sebelum mengambil keputusan investasi.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function SettingsPage() {
  return (
    <div className="p-6 space-y-8 max-w-2xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Data & Settings</h1>
        <p className="text-xs text-gray-500 mt-0.5">Status sistem, manajemen data, dan konfigurasi</p>
      </div>

      <DataHealthSection />
      <BootstrapSection />
      <AboutSection />
    </div>
  );
}
