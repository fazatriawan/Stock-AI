"use client";

import React, { useEffect, useRef, useState } from "react";
import { api, type DataProvidersResponse, type CSVImportResult, type CoverageStatus, type ProviderQuotaStatus, type DataGapsStatus, type GapReportRow, type HealGapsResult, type JobHistoryStatus, type JobRunRow, type PlatformHealthSummary } from "@/lib/api";
import { CheckCircle, XCircle, AlertCircle, RefreshCw, Database, Wifi, WifiOff, ChevronRight, Upload, ShieldCheck, Lock } from "lucide-react";

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

function LicenseBadge({ license }: { license: string }) {
  if (license === "FREE_PERSONAL") return (
    <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border bg-sky-950/30 text-sky-400 border-sky-800/40">
      <ShieldCheck size={9} /> GRATIS
    </span>
  );
  if (license === "PAID") return (
    <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border bg-amber-950/30 text-amber-400 border-amber-800/40">
      <Lock size={9} /> BERBAYAR
    </span>
  );
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-gray-800 text-gray-500 border-gray-700">
      {license}
    </span>
  );
}

function AccessBadge({ access }: { access: string }) {
  if (access === "ACTIVE") return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-emerald-950/20 text-emerald-400 border-emerald-800/30">AKTIF</span>
  );
  if (access === "NOT_CONFIGURED") return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-gray-800 text-gray-500 border-gray-700">BELUM DIKONFIGURASI</span>
  );
  if (access === "LICENSE_BLOCKED") return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-red-950/20 text-red-400 border-red-800/30">DIBLOKIR BUDGET</span>
  );
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border bg-gray-800 text-gray-500 border-gray-700">{access}</span>
  );
}

// ---------------------------------------------------------------------------
// Platform health widget — FREE-21
// ---------------------------------------------------------------------------
function GradeRing({ grade, score }: { grade: string; score: number }) {
  const color =
    grade === "A" ? "text-emerald-400 border-emerald-500/50" :
    grade === "B" ? "text-blue-400 border-blue-500/50" :
    grade === "C" ? "text-amber-400 border-amber-500/50" :
    grade === "D" ? "text-orange-400 border-orange-500/50" :
    "text-red-400 border-red-500/50";
  return (
    <div className={`flex flex-col items-center justify-center w-16 h-16 rounded-full border-2 ${color}`}>
      <span className={`text-xl font-bold ${color.split(" ")[0]}`}>{grade}</span>
      <span className="text-[10px] text-gray-500">{score}/100</span>
    </div>
  );
}

function ScoreBar({ label, score, max, color }: { label: string; score: number; max: number; color: string }) {
  const pct = Math.round((score / max) * 100);
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-[11px]">
        <span className="text-gray-400">{label}</span>
        <span className="text-gray-500">{score}/{max}</span>
      </div>
      <div className="h-1.5 bg-gray-700/60 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function PlatformHealthWidget() {
  const [health, setHealth] = useState<PlatformHealthSummary | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const r = await api.admin.healthSummary();
      setHealth(r);
    } catch {
      // best-effort — don't block page if DB empty
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (!health && !loading) return null;
  if (loading && !health) return (
    <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 animate-pulse h-24" />
  );
  if (!health) return null;

  const issues: string[] = [];
  if (health.freshness.fresh_pct < 80) issues.push(`${health.freshness.fresh_pct}% bar fresh`);
  if (health.gaps.critical_count > 0) issues.push(`${health.gaps.critical_count} gap CRITICAL`);
  if (health.quota.exhausted_providers.length > 0) issues.push(`${health.quota.exhausted_providers.join(", ")} kuota habis`);
  if (health.jobs.error_count > 0) issues.push(`${health.jobs.error_count} job error`);

  return (
    <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4">
      <div className="flex items-start gap-4">
        <GradeRing grade={health.grade} score={health.overall_score} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-200">Kesehatan Platform</span>
            <button
              onClick={load}
              disabled={loading}
              className="text-[10px] text-gray-500 hover:text-gray-300 disabled:opacity-40 transition-colors"
            >
              <RefreshCw size={10} className={loading ? "animate-spin inline" : "inline"} />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            <ScoreBar label="Freshness" score={health.freshness.score} max={40}
              color={health.freshness.score >= 32 ? "bg-emerald-500" : health.freshness.score >= 20 ? "bg-amber-500" : "bg-red-500"} />
            <ScoreBar label="Data Gaps" score={health.gaps.score} max={25}
              color={health.gaps.score >= 20 ? "bg-emerald-500" : health.gaps.score >= 10 ? "bg-amber-500" : "bg-red-500"} />
            <ScoreBar label="Quota" score={health.quota.score} max={20}
              color={health.quota.score === 20 ? "bg-emerald-500" : "bg-amber-500"} />
            <ScoreBar label="Jobs" score={health.jobs.score} max={15}
              color={health.jobs.score === 15 ? "bg-emerald-500" : health.jobs.score >= 10 ? "bg-amber-500" : "bg-red-500"} />
          </div>
          {issues.length > 0 && (
            <p className="text-[11px] text-amber-400/80 mt-2">
              ⚠ {issues.join(" · ")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data Health section
// ---------------------------------------------------------------------------
function DataHealthSection() {
  const [data, setData] = useState<DataProvidersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [staleResult, setStaleResult] = useState<{ marked_stale: number; cutoff_date: string } | null>(null);
  const [markingStale, setMarkingStale] = useState(false);
  const [refreshResult, setRefreshResult] = useState<{ instruments_refreshed: number; bars_added: number; errors: string[] } | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  function load() {
    setLoading(true);
    setError(null);
    api.data.providers()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  async function handleMarkStale() {
    setMarkingStale(true);
    setStaleResult(null);
    try {
      const r = await api.data.markStale();
      setStaleResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menandai data lama");
    } finally {
      setMarkingStale(false);
    }
  }

  async function handleRefreshStale() {
    setRefreshing(true);
    setRefreshResult(null);
    try {
      const r = await api.data.refreshStale();
      setRefreshResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal refresh data");
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(load, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-300">Status Provider Data</h2>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRefreshStale}
            disabled={refreshing}
            title="Re-ingest instrumen dengan bar STALE via yfinance"
            className="text-xs text-blue-500/70 hover:text-blue-400 flex items-center gap-1 transition-colors disabled:opacity-50"
          >
            {refreshing ? <RefreshCw size={11} className="animate-spin" /> : <RefreshCw size={11} />}
            Refresh Stale
          </button>
          <button
            onClick={handleMarkStale}
            disabled={markingStale}
            title="Tandai bar harga kadaluarsa sebagai STALE"
            className="text-xs text-amber-500/70 hover:text-amber-400 flex items-center gap-1 transition-colors disabled:opacity-50"
          >
            {markingStale ? <RefreshCw size={11} className="animate-spin" /> : <Database size={11} />}
            Tandai Stale
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>
      {staleResult && (
        <div className="rounded-lg border border-amber-800/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-400">
          {staleResult.marked_stale} bar ditandai STALE (cutoff: {staleResult.cutoff_date})
        </div>
      )}
      {refreshResult && (
        <div className={`rounded-lg border px-3 py-2 text-xs space-y-0.5 ${
          refreshResult.errors.length > 0
            ? "border-amber-800/40 bg-amber-950/20 text-amber-400"
            : "border-emerald-800/40 bg-emerald-950/20 text-emerald-400"
        }`}>
          <p>✓ {refreshResult.instruments_refreshed} instrumen di-refresh · {refreshResult.bars_added} bar baru</p>
          {refreshResult.errors.length > 0 && (
            <p className="text-red-400/80">{refreshResult.errors.length} error: {refreshResult.errors[0]}</p>
          )}
        </div>
      )}

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
                  <StatusIcon status={p.health_status} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-gray-200 capitalize">{p.provider}</span>
                      <StatusBadge status={p.health_status} />
                      <LicenseBadge license={p.license_status} />
                      <AccessBadge access={p.access_status} />
                    </div>
                    {p.datasets.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {p.datasets.map(d => (
                          <span key={d} className="text-[9px] px-1.5 py-0.5 rounded bg-gray-700/50 text-gray-400 border border-gray-700/30">
                            {d}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex gap-3 mt-1 text-[10px] text-gray-600">
                      <span>{p.granularity}</span>
                      <span>·</span>
                      <span>{p.freshness_policy}</span>
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
// FREE-13: Coverage dashboard
// ---------------------------------------------------------------------------
function CoverageSection() {
  const [data, setData] = useState<CoverageStatus | null>(null);
  const [resetting, setResetting] = useState(false);
  const [toast, setToast] = useState<{ type: "ok" | "err"; msg: string } | null>(null);

  function load() {
    api.data.coverage().then(setData).catch(() => {});
  }

  useEffect(() => { load(); }, []);

  async function resetQuota() {
    setResetting(true);
    setToast(null);
    try {
      const r = await api.data.resetQuota();
      setToast({ type: "ok", msg: `${r.bars_reset} bar di-reset ke STALE — siap di-refresh malam ini.` });
      load();
    } catch (ex) {
      setToast({ type: "err", msg: ex instanceof Error ? ex.message : "Gagal reset" });
    } finally {
      setResetting(false);
    }
  }

  const pct = (n: number) => data && data.total > 0 ? Math.round(n / data.total * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-300">Coverage & Freshness</h2>
        <button onClick={load} className="text-gray-500 hover:text-gray-300">
          <RefreshCw size={12} />
        </button>
      </div>

      {data ? (
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 space-y-3">
          {/* Bar chart distribusi */}
          <div className="space-y-2">
            {[
              { label: "Fresh",           val: data.fresh,           color: "bg-emerald-500" },
              { label: "Stale",           val: data.stale,           color: "bg-amber-500" },
              { label: "Unavailable",     val: data.unavailable,     color: "bg-gray-600" },
              { label: "Quota Exhausted", val: data.quota_exhausted, color: "bg-red-700" },
            ].map(({ label, val, color }) => (
              <div key={label} className="flex items-center gap-2 text-xs">
                <span className="w-28 text-gray-400 shrink-0">{label}</span>
                <div className="flex-1 bg-gray-700/40 rounded-full h-1.5">
                  <div
                    className={`${color} h-1.5 rounded-full transition-all`}
                    style={{ width: `${pct(val)}%` }}
                  />
                </div>
                <span className="w-12 text-right text-gray-400 tabular-nums">{val.toLocaleString("id-ID")}</span>
              </div>
            ))}
          </div>

          {/* Summary row */}
          <div className="flex flex-wrap gap-4 text-xs text-gray-500 pt-1 border-t border-gray-700/30">
            <span>Total <strong className="text-gray-300">{data.total.toLocaleString("id-ID")}</strong> bar</span>
            <span>Stale <strong className="text-amber-400">{data.stale_pct}%</strong></span>
            {data.unavailable_instruments > 0 && (
              <span className="text-gray-500">{data.unavailable_instruments} instrumen unavailable</span>
            )}
            {data.quota_instruments > 0 && (
              <span className="text-red-400">{data.quota_instruments} instrumen quota exhausted</span>
            )}
          </div>

          {/* Reset quota action */}
          {data.quota_exhausted > 0 && (
            <button
              onClick={resetQuota}
              disabled={resetting}
              className="w-full text-xs py-2 bg-red-900/40 hover:bg-red-900/60 border border-red-800/40 text-red-300 rounded-lg disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
            >
              {resetting
                ? <><RefreshCw size={12} className="animate-spin" /> Mereset...</>
                : `Reset ${data.quota_exhausted.toLocaleString("id-ID")} bar quota exhausted → STALE`}
            </button>
          )}
        </div>
      ) : (
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 text-xs text-gray-500 text-center">
          Memuat coverage...
        </div>
      )}

      {toast && (
        <div className={`rounded-lg border px-3 py-2 text-xs ${
          toast.type === "ok"
            ? "border-emerald-800/40 bg-emerald-950/20 text-emerald-400"
            : "border-red-800/40 bg-red-950/20 text-red-400"
        }`}>
          {toast.type === "ok" ? "✓ " : "✗ "}{toast.msg}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CSV Import section
// ---------------------------------------------------------------------------
function CSVImportSection() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [instrumentId, setInstrumentId] = useState("");
  const [provider, setProvider] = useState("csv_manual");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CSVImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) { setError("Pilih file CSV terlebih dahulu"); return; }
    if (!instrumentId.trim()) { setError("Instrument ID wajib diisi (contoh: BBCA.JK)"); return; }

    setLoading(true);
    setError(null);
    setResult(null);

    const fd = new FormData();
    fd.append("file", file);
    fd.append("instrument_id", instrumentId.trim());
    fd.append("provider", provider.trim() || "csv_manual");

    try {
      const r = await api.data.importCSV(fd);
      setResult(r);
      if (fileRef.current) fileRef.current.value = "";
    } catch (ex) {
      setError(ex instanceof Error ? ex.message : "Gagal import");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-gray-300">Import Harga Historis (CSV)</h2>
      <p className="text-xs text-gray-500">
        Upload file CSV dengan kolom <code className="bg-gray-800 px-1 rounded">date, close</code> (minimal).
        Kolom opsional: <code className="bg-gray-800 px-1 rounded">open, high, low, volume, adj_close</code>.
        Import bersifat idempoten — file yang sama tidak akan diproses ulang.
      </p>

      <form onSubmit={handleSubmit} className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Instrument ID <span className="text-red-400">*</span></label>
            <input
              type="text"
              value={instrumentId}
              onChange={e => setInstrumentId(e.target.value)}
              placeholder="cth. BBCA.JK atau AAPL"
              className="w-full bg-gray-900/60 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-700/60"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Label Provider</label>
            <input
              type="text"
              value={provider}
              onChange={e => setProvider(e.target.value)}
              placeholder="csv_manual"
              className="w-full bg-gray-900/60 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-700/60"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs text-gray-400 mb-1">File CSV <span className="text-red-400">*</span></label>
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="block w-full text-xs text-gray-400 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:bg-gray-700 file:text-gray-200 hover:file:bg-gray-600 cursor-pointer"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="flex items-center gap-2 text-sm px-4 py-2 bg-blue-700 hover:bg-blue-600 text-white rounded-lg disabled:opacity-50 transition-colors"
        >
          {loading ? <RefreshCw size={13} className="animate-spin" /> : <Upload size={13} />}
          {loading ? "Mengimpor..." : "Import"}
        </button>
      </form>

      {error && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      {result && (
        <div className={`rounded-lg border px-4 py-3 space-y-1.5 ${
          result.skipped_existing_source
            ? "border-amber-800/40 bg-amber-950/20"
            : "border-emerald-800/40 bg-emerald-950/20"
        }`}>
          {result.skipped_existing_source ? (
            <p className="text-xs text-amber-400">File ini sudah pernah diimpor sebelumnya — tidak ada perubahan.</p>
          ) : (
            <p className="text-xs text-emerald-400">
              ✓ {result.inserted} baris diimpor · {result.skipped_duplicate} duplikat dilewati
            </p>
          )}
          {result.parse_errors.length > 0 && (
            <div>
              <p className="text-xs text-amber-400 mb-1">{result.parse_errors.length} baris bermasalah:</p>
              <ul className="text-[10px] text-amber-500/80 space-y-0.5 max-h-32 overflow-y-auto">
                {result.parse_errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bootstrap section
// ---------------------------------------------------------------------------
function BootstrapSection() {
  const [status, setStatus] = useState<{ instruments_loaded: number; price_bars: number; yfinance_enabled: boolean; is_ready: boolean } | null>(null);
  const [loading, setLoading] = useState<"live" | "mock" | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function loadStatus() {
    api.admin.setupStatus()
      .then(setStatus)
      .catch(() => setError("Gagal memuat status — pastikan API berjalan"));
  }

  useEffect(() => { loadStatus(); }, []);

  async function runBootstrap(useMock: boolean) {
    setLoading(useMock ? "mock" : "live");
    setResult(null);
    setError(null);
    try {
      const r = await api.admin.bootstrap(useMock);
      setResult(`${r.instruments_loaded} instrumen dimuat. Harga historis sedang diunduh di background.`);
      loadStatus();
    } catch (ex) {
      setError(ex instanceof Error ? ex.message : "Gagal bootstrap");
    } finally {
      setLoading(null);
    }
  }

  const isReady = status?.is_ready ?? false;

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-gray-300">Setup Data Pasar</h2>

      {/* Status bar */}
      <div className={`flex items-center gap-3 rounded-xl px-4 py-3 border ${
        isReady
          ? "bg-emerald-950/20 border-emerald-800/40"
          : "bg-amber-950/20 border-amber-800/40"
      }`}>
        {isReady
          ? <CheckCircle size={16} className="text-emerald-400 shrink-0" />
          : <AlertCircle size={16} className="text-amber-400 shrink-0" />}
        <div className="flex-1 min-w-0">
          {isReady ? (
            <p className="text-sm text-emerald-300">
              {status!.instruments_loaded} instrumen siap ·{" "}
              {status!.price_bars.toLocaleString("id-ID")} bar harga
            </p>
          ) : (
            <p className="text-sm text-amber-300">
              Data belum dimuat — screener dan decision center belum bisa dipakai
            </p>
          )}
        </div>
        <button onClick={loadStatus} className="text-gray-500 hover:text-gray-300">
          <RefreshCw size={12} />
        </button>
      </div>

      {/* Options */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Live */}
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 space-y-3">
          <div className="flex items-start gap-3">
            <Wifi size={16} className="text-blue-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-200">Data Live (Rekomendasi)</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Muat saham IDX + US dari yfinance. Butuh koneksi internet.
                Harga historis 1 tahun diunduh di background (~1–3 menit).
              </p>
              {status && !status.yfinance_enabled && (
                <p className="text-xs text-amber-400 mt-1.5">
                  ⚠ YFINANCE_ENABLED belum aktif di .env — akan fallback ke mock
                </p>
              )}
            </div>
          </div>
          <button
            onClick={() => runBootstrap(false)}
            disabled={loading !== null}
            className="w-full text-sm py-2 bg-blue-700 hover:bg-blue-600 text-white rounded-lg disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {loading === "live"
              ? <><RefreshCw size={13} className="animate-spin" /> Memuat...</>
              : <><ChevronRight size={13} /> Muat Data Live</>}
          </button>
        </div>

        {/* Mock */}
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 space-y-3">
          <div className="flex items-start gap-3">
            <WifiOff size={16} className="text-gray-500 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-300">Data Contoh (Offline)</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Pakai data sintetis — untuk testing tanpa internet.
                Angka tidak mencerminkan kondisi pasar nyata.
              </p>
            </div>
          </div>
          <button
            onClick={() => runBootstrap(true)}
            disabled={loading !== null}
            className="w-full text-sm py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {loading === "mock"
              ? <><RefreshCw size={13} className="animate-spin" /> Memuat...</>
              : "Muat Data Contoh"}
          </button>
        </div>
      </div>

      {result && (
        <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 px-3 py-2 text-xs text-emerald-400">
          ✓ {result}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FREE-11: Market bootstrap section — IDX + US per-market seed
// ---------------------------------------------------------------------------
type BootstrapJob = "idx" | "us" | null;

function MarketBootstrapSection() {
  const [status, setStatus] = useState<{ instruments_loaded: number; price_bars: number } | null>(null);
  const [loading, setLoading] = useState<BootstrapJob>(null);
  const [toast, setToast] = useState<{ type: "ok" | "err"; msg: string } | null>(null);

  function refreshStatus() {
    api.admin.setupStatus().then(setStatus).catch(() => {});
  }

  useEffect(() => { refreshStatus(); }, []);

  async function trigger(market: "idx" | "us") {
    setLoading(market);
    setToast(null);
    try {
      const r = market === "idx"
        ? await api.admin.bootstrapIDX()
        : await api.admin.bootstrapUS();
      setToast({ type: "ok", msg: r.message });
      setTimeout(refreshStatus, 3000);
    } catch (ex) {
      setToast({ type: "err", msg: ex instanceof Error ? ex.message : "Gagal" });
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-300">Bootstrap Instrumen</h2>
        {status && (
          <span className="text-xs text-gray-500">
            {status.instruments_loaded} instrumen · {status.price_bars.toLocaleString("id-ID")} bar
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* IDX */}
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 space-y-3">
          <div>
            <p className="text-sm font-medium text-gray-200">IDX (~200 saham)</p>
            <p className="text-xs text-gray-500 mt-0.5">
              LQ45 · IDX80 · sektoral pilihan. Histori 5 tahun via yfinance.
              Berjalan di background ~5–15 menit.
            </p>
          </div>
          <button
            onClick={() => trigger("idx")}
            disabled={loading !== null}
            className="w-full text-sm py-2 bg-emerald-800 hover:bg-emerald-700 text-white rounded-lg disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {loading === "idx"
              ? <><RefreshCw size={13} className="animate-spin" /> Memuat...</>
              : <><Database size={13} /> Bootstrap IDX</>}
          </button>
        </div>

        {/* US */}
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 space-y-3">
          <div>
            <p className="text-sm font-medium text-gray-200">US (~90 saham + ETF)</p>
            <p className="text-xs text-gray-500 mt-0.5">
              S&amp;P 500 pilihan · ETF likuid (SPY, QQQ, GLD). Histori 5 tahun via yfinance.
              Berjalan di background ~3–10 menit.
            </p>
          </div>
          <button
            onClick={() => trigger("us")}
            disabled={loading !== null}
            className="w-full text-sm py-2 bg-blue-800 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {loading === "us"
              ? <><RefreshCw size={13} className="animate-spin" /> Memuat...</>
              : <><Database size={13} /> Bootstrap US</>}
          </button>
        </div>
      </div>

      {toast && (
        <div className={`rounded-lg border px-3 py-2 text-xs ${
          toast.type === "ok"
            ? "border-emerald-800/40 bg-emerald-950/20 text-emerald-400"
            : "border-red-800/40 bg-red-950/20 text-red-400"
        }`}>
          {toast.type === "ok" ? "✓ " : "✗ "}{toast.msg}
        </div>
      )}

      <p className="text-xs text-gray-600">
        Bootstrap berjalan sekali — data yang sudah ada tidak dihapus (upsert idempoten).
        Jalankan ulang kapan saja untuk mengisi gap data.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FREE-17: Data Gap section — instrumen dengan OHLCV tidak lengkap
// ---------------------------------------------------------------------------
function SeverityBadge({ severity }: { severity: GapReportRow["severity"] }) {
  const map: Record<string, string> = {
    CRITICAL: "bg-red-900/30 text-red-400 border-red-800/40",
    WARNING:  "bg-amber-900/30 text-amber-400 border-amber-800/40",
    OK:       "bg-emerald-900/20 text-emerald-400 border-emerald-800/30",
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${map[severity] ?? "bg-gray-700 text-gray-400 border-gray-600"}`}>
      {severity}
    </span>
  );
}

function DataGapsSection() {
  const [data, setData] = useState<DataGapsStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [healing, setHealing] = useState(false);
  const [healResult, setHealResult] = useState<HealGapsResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api.data.gaps()
      .then(setData)
      .catch(() => setError("Gagal memuat data gap"))
      .finally(() => setLoading(false));
  }

  async function handleHeal() {
    setHealing(true);
    setHealResult(null);
    setError(null);
    try {
      const r = await api.data.healGaps();
      setHealResult(r);
      load(); // refresh gap list
    } catch {
      setError("Gagal menjalankan auto-heal");
    } finally {
      setHealing(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-gray-300">Data Gap</h2>
          <p className="text-[11px] text-gray-500 mt-0.5">Instrumen dengan bar OHLCV kurang dari ekspektasi</p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <span className="text-xs text-gray-500">
              {data.with_gaps} / {data.instruments_checked} instrumen
            </span>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="text-xs text-gray-500 hover:text-gray-300 disabled:opacity-40 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && (
        <div className="text-xs px-3 py-2 rounded-lg border bg-red-900/20 border-red-800/40 text-red-400">
          {error}
        </div>
      )}

      <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl overflow-hidden">
        {loading && !data ? (
          <div className="p-4 text-xs text-gray-500 text-center">Menghitung gap…</div>
        ) : !data || data.reports.length === 0 ? (
          <div className="p-4 text-xs text-gray-500 text-center">
            {data ? "Tidak ada gap terdeteksi — semua instrumen terlihat lengkap." : "Belum ada data."}
          </div>
        ) : (
          <div className="divide-y divide-gray-700/30">
            <div className="grid grid-cols-[1fr_auto_auto_auto] gap-2 px-4 py-2 text-[10px] text-gray-500 uppercase tracking-wide">
              <span>Instrumen</span>
              <span className="text-right">Bar</span>
              <span className="text-right">Gap</span>
              <span>Status</span>
            </div>
            {data.reports.slice(0, 20).map((r) => (
              <div key={r.instrument_id} className="grid grid-cols-[1fr_auto_auto_auto] gap-2 px-4 py-2.5 items-center">
                <div>
                  <span className="text-xs font-medium text-gray-200">{r.canonical_symbol}</span>
                  <span className="text-[10px] text-gray-500 ml-1.5">{r.exchange}</span>
                </div>
                <div className="text-xs text-right text-gray-400 tabular-nums">
                  {r.bar_count.toLocaleString()} / {r.expected_bars.toLocaleString()}
                </div>
                <div className={`text-xs text-right tabular-nums font-medium ${
                  r.severity === "CRITICAL" ? "text-red-400" : r.severity === "WARNING" ? "text-amber-400" : "text-gray-400"
                }`}>
                  {r.gap_pct.toFixed(1)}%
                </div>
                <SeverityBadge severity={r.severity} />
              </div>
            ))}
            {data.reports.length > 20 && (
              <div className="px-4 py-2 text-[11px] text-gray-500 text-center">
                +{data.reports.length - 20} instrumen lainnya
              </div>
            )}
          </div>
        )}
      </div>

      {healResult && (
        <div className="bg-emerald-900/20 border border-emerald-800/40 rounded-lg px-3 py-2.5 text-xs text-emerald-300 space-y-0.5">
          <p className="font-medium">Auto-heal selesai</p>
          <p className="text-emerald-400/70">
            {healResult.instruments_healed}/{healResult.instruments_found} instrumen diperbaiki
            · {healResult.bars_added.toLocaleString()} bar ditambahkan
          </p>
          {healResult.errors.length > 0 && (
            <p className="text-amber-400/70">{healResult.errors.length} error (lihat log API)</p>
          )}
        </div>
      )}

      {data && data.with_gaps > 0 && (
        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] text-gray-500">
            {data.with_gaps} instrumen terdeteksi gap. Re-ingest via provider gratis tersedia.
          </p>
          <button
            onClick={handleHeal}
            disabled={healing || loading}
            className="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-sky-700/30 border border-sky-600/40 text-sky-300 hover:bg-sky-700/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {healing ? "Memperbaiki…" : "Perbaiki Otomatis"}
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FREE-16: Provider Quota section — daily call counter per provider
// ---------------------------------------------------------------------------
function ProviderQuotaSection() {
  const [data, setData] = useState<ProviderQuotaStatus | null>(null);
  const [resetting, setResetting] = useState(false);
  const [toast, setToast] = useState<{ type: "ok" | "err"; msg: string } | null>(null);

  function load() {
    api.data.providerQuota().then(setData).catch(() => {});
  }

  useEffect(() => { load(); }, []);

  async function handleReset() {
    setResetting(true);
    setToast(null);
    try {
      await api.admin.resetQuotaTracker();
      setToast({ type: "ok", msg: "Counter direset — semua provider kembali ke 0 panggilan." });
      load();
    } catch {
      setToast({ type: "err", msg: "Gagal reset counter." });
    } finally {
      setResetting(false);
    }
  }

  const anyExhausted = data?.providers.some((p) => p.quota_exhausted) ?? false;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-300">Panggilan Provider Hari Ini</h2>
        <div className="flex items-center gap-2">
          {data && (
            <span className="text-xs text-gray-500">
              Total: <span className="text-gray-300 font-medium">{data.total_calls_today}</span>
            </span>
          )}
          <button
            onClick={load}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={12} />
          </button>
        </div>
      </div>

      {toast && (
        <div className={`text-xs px-3 py-2 rounded-lg border ${
          toast.type === "ok"
            ? "bg-emerald-900/20 border-emerald-800/40 text-emerald-400"
            : "bg-red-900/20 border-red-800/40 text-red-400"
        }`}>
          {toast.msg}
        </div>
      )}

      <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl overflow-hidden">
        {!data ? (
          <div className="p-4 text-xs text-gray-500 text-center">Memuat statistik provider…</div>
        ) : data.providers.length === 0 ? (
          <div className="p-4 text-xs text-gray-500 text-center">
            Belum ada panggilan provider hari ini. Counter akan terisi saat refresh data berjalan.
          </div>
        ) : (
          <div className="divide-y divide-gray-700/30">
            {data.providers.map((p) => {
              const pct = p.quota_per_day ? Math.min(100, Math.round(p.calls_today / p.quota_per_day * 100)) : null;
              return (
                <div key={p.provider_name} className="px-4 py-3">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-gray-200">{p.provider_name}</span>
                      {p.quota_exhausted && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded border bg-red-900/30 text-red-400 border-red-800/40">
                          QUOTA HABIS
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-gray-400">
                      <span className="text-gray-200 font-medium">{p.calls_today}</span>
                      {p.quota_per_day !== null && (
                        <span className="text-gray-500"> / {p.quota_per_day}</span>
                      )}
                      <span className="text-gray-600"> panggilan</span>
                    </div>
                  </div>
                  {pct !== null && (
                    <div className="w-full bg-gray-700/40 rounded-full h-1">
                      <div
                        className={`h-1 rounded-full transition-all ${
                          pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-amber-500" : "bg-emerald-500"
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {anyExhausted && (
        <div className="bg-amber-900/10 border border-amber-800/30 rounded-lg px-3 py-2.5 flex items-center justify-between gap-3">
          <p className="text-xs text-amber-300/80">
            Ada provider yang quota harian-nya habis. Reset counter agar percobaan ulang bisa berjalan malam ini.
          </p>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-amber-700/30 border border-amber-600/40 text-amber-300 hover:bg-amber-700/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {resetting ? "…" : "Reset Counter"}
          </button>
        </div>
      )}

      <p className="text-[11px] text-gray-600">
        Counter reset otomatis setiap pergantian hari. Tanggal: {data?.providers[0]?.date_str ?? "—"}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scheduler jobs section — FREE-20
// ---------------------------------------------------------------------------
function StatusDot({ status }: { status: string }) {
  if (status === "ok") return <span className="inline-block w-2 h-2 rounded-full bg-emerald-500" />;
  if (status === "error") return <span className="inline-block w-2 h-2 rounded-full bg-red-500" />;
  if (status === "running") return <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />;
  return <span className="inline-block w-2 h-2 rounded-full bg-gray-600" />;
}

// ---------------------------------------------------------------------------
// Stale instruments section — FREE-22
// ---------------------------------------------------------------------------
function StaleInstrumentsSection() {
  const [data, setData] = useState<import("@/lib/api").StaleInstrumentsStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<import("@/lib/api").BatchRefreshResponse | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.data.staleInstruments(30);
      setData(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat daftar instrumen stale");
    } finally {
      setLoading(false);
    }
  }

  async function handleRefreshAll() {
    if (!data) return;
    setRefreshing(true);
    setRefreshResult(null);
    try {
      const symbols = data.instruments.map((i) => i.canonical_symbol);
      const r = await api.data.refreshBatch(symbols, symbols.length);
      setRefreshResult(r);
      // reload stale list to reflect changes
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menjalankan batch refresh");
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (!data && !loading && !error) return null;
  if (data && data.total_instruments === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-300">
          Instrumen Stale
          {data && data.total_instruments > 0 && (
            <span className="ml-2 text-[11px] text-amber-400 font-normal">
              ({data.total_instruments} instrumen · {data.total_stale_bars.toLocaleString()} bar)
            </span>
          )}
        </h2>
        <div className="flex items-center gap-2">
          {data && data.total_instruments > 0 && (
            <button
              onClick={handleRefreshAll}
              disabled={refreshing || loading}
              className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-blue-700/60 bg-blue-900/20 text-blue-400 hover:text-blue-200 hover:border-blue-500 disabled:opacity-40 transition-colors"
            >
              <RefreshCw size={10} className={refreshing ? "animate-spin" : ""} />
              {refreshing ? "Menyegarkan…" : "Segarkan Semua"}
            </button>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-gray-700/60 bg-gray-800/50 text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors"
          >
            <RefreshCw size={10} className={loading ? "animate-spin" : ""} />
            Muat ulang
          </button>
        </div>
      </div>

      {refreshResult && (
        <div className={`text-[11px] px-3 py-2 rounded-lg border ${
          refreshResult.failed === 0
            ? "bg-emerald-900/15 border-emerald-800/40 text-emerald-400"
            : "bg-amber-900/15 border-amber-800/40 text-amber-400"
        }`}>
          Selesai: {refreshResult.succeeded} berhasil · {refreshResult.failed} gagal · +{refreshResult.total_bars_added.toLocaleString()} bar baru
        </div>
      )}

      {error && (
        <p className="text-xs text-red-400 px-3 py-2 rounded-lg bg-red-950/20 border border-red-800/40">{error}</p>
      )}

      {loading && !data && (
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl h-24 animate-pulse" />
      )}

      {data && data.instruments.length > 0 && (
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-700/40">
                <th className="text-left px-3 py-2 text-gray-500 font-normal">Ticker</th>
                <th className="text-left px-3 py-2 text-gray-500 font-normal">Bursa</th>
                <th className="text-right px-3 py-2 text-gray-500 font-normal">Stale</th>
                <th className="text-right px-3 py-2 text-gray-500 font-normal">Total</th>
                <th className="text-right px-3 py-2 text-gray-500 font-normal">Stale%</th>
                <th className="text-left px-3 py-2 text-gray-500 font-normal">FRESH terakhir</th>
              </tr>
            </thead>
            <tbody>
              {data.instruments.map((row) => (
                <tr key={row.instrument_id} className="border-b border-gray-700/20 last:border-0 hover:bg-gray-700/20 transition-colors">
                  <td className="px-3 py-2 font-mono text-gray-300">{row.canonical_symbol}</td>
                  <td className="px-3 py-2 text-gray-500">{row.exchange}</td>
                  <td className="px-3 py-2 text-right text-amber-400">{row.stale_count.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right text-gray-400">{row.total_count.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right">
                    <span className={row.stale_pct >= 50 ? "text-red-400" : "text-amber-400"}>
                      {row.stale_pct}%
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-500">
                    {row.last_fresh_date ?? <span className="text-red-400/70">tidak ada</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ProviderStatsSection() {
  const [data, setData] = useState<import("@/lib/api").ProviderSuccessResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await api.data.providerStats());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat provider stats");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (!data && !loading && !error) return null;
  if (data && data.providers.length === 0) return null;

  function rateColor(rate: number) {
    if (rate >= 90) return "text-emerald-400";
    if (rate >= 60) return "text-amber-400";
    return "text-red-400";
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-300">Provider Success Rate</h2>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-gray-700/60 bg-gray-800/50 text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors"
        >
          <RefreshCw size={10} className={loading ? "animate-spin" : ""} />
          Muat ulang
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-400 px-3 py-2 rounded-lg bg-red-950/20 border border-red-800/40">{error}</p>
      )}

      {loading && !data && (
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl h-20 animate-pulse" />
      )}

      {data && data.providers.length > 0 && (
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-700/40">
                <th className="text-left px-3 py-2 text-gray-500 font-normal">Provider</th>
                <th className="text-right px-3 py-2 text-gray-500 font-normal">Panggilan</th>
                <th className="text-right px-3 py-2 text-gray-500 font-normal">Sukses</th>
                <th className="text-right px-3 py-2 text-gray-500 font-normal">Gagal</th>
                <th className="text-right px-3 py-2 text-gray-500 font-normal">Rate</th>
                <th className="text-right px-3 py-2 text-gray-500 font-normal">Bar</th>
                <th className="text-left px-3 py-2 text-gray-500 font-normal">Error terakhir</th>
              </tr>
            </thead>
            <tbody>
              {data.providers.map((row) => (
                <tr key={row.provider_name} className="border-b border-gray-700/20 last:border-0 hover:bg-gray-700/20 transition-colors">
                  <td className="px-3 py-2 font-mono text-gray-300">{row.provider_name}</td>
                  <td className="px-3 py-2 text-right text-gray-400">{row.total_calls}</td>
                  <td className="px-3 py-2 text-right text-emerald-400">{row.calls_succeeded}</td>
                  <td className="px-3 py-2 text-right text-red-400">{row.calls_failed}</td>
                  <td className={`px-3 py-2 text-right font-medium ${rateColor(row.success_rate)}`}>
                    {row.total_calls === 0 ? "—" : `${row.success_rate}%`}
                  </td>
                  <td className="px-3 py-2 text-right text-gray-500">{row.bars_fetched.toLocaleString()}</td>
                  <td className="px-3 py-2 text-gray-600 max-w-[180px] truncate" title={row.last_error ?? undefined}>
                    {row.last_error ? (
                      <span className="text-red-400/70">{row.last_error}</span>
                    ) : (
                      <span className="text-gray-700">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-3 py-1.5 text-[10px] text-gray-700 border-t border-gray-700/20">
            Reset otomatis setiap tengah malam · hanya exception dihitung sebagai gagal
          </div>
        </div>
      )}
    </div>
  );
}

function SchedulerJobsSection() {
  const [status, setStatus] = useState<JobHistoryStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.admin.jobHistory();
      setStatus(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat riwayat job");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function fmtDuration(ms: number | null) {
    if (ms === null) return "—";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  function summaryText(row: JobRunRow) {
    const s = row.summary;
    if (!s || Object.keys(s).length === 0) return null;
    return Object.entries(s)
      .filter(([, v]) => v !== undefined && v !== null)
      .map(([k, v]) => `${k}=${v}`)
      .join(" · ");
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-300">Riwayat Scheduler</h2>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-gray-700/60 bg-gray-800/50 text-gray-400 hover:text-gray-200 hover:border-gray-600 disabled:opacity-40 transition-colors"
        >
          <RefreshCw size={10} className={loading ? "animate-spin" : ""} />
          Muat ulang
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-400 px-3 py-2 rounded-lg bg-red-950/20 border border-red-800/40">{error}</p>
      )}

      {!status && !loading && !error && (
        <p className="text-xs text-gray-600">Belum ada data. Klik "Muat ulang".</p>
      )}

      {status && status.jobs.length === 0 && (
        <p className="text-xs text-gray-600">
          Belum ada job yang berjalan sejak server terakhir start.
        </p>
      )}

      {status && status.jobs.length > 0 && (
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-700/40">
                <th className="text-left px-3 py-2 text-gray-500 font-normal">Job</th>
                <th className="text-left px-3 py-2 text-gray-500 font-normal">Status</th>
                <th className="text-left px-3 py-2 text-gray-500 font-normal">Durasi</th>
                <th className="text-left px-3 py-2 text-gray-500 font-normal">Terakhir</th>
                <th className="text-left px-3 py-2 text-gray-500 font-normal">Detail</th>
              </tr>
            </thead>
            <tbody>
              {status.jobs.map((row) => (
                <tr key={row.job_name} className="border-b border-gray-700/20 last:border-0">
                  <td className="px-3 py-2 font-mono text-gray-300">{row.job_name}</td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1.5">
                      <StatusDot status={row.status} />
                      <span className={
                        row.status === "ok" ? "text-emerald-400" :
                        row.status === "error" ? "text-red-400" :
                        row.status === "running" ? "text-amber-400" : "text-gray-500"
                      }>
                        {row.status}
                      </span>
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-400">{fmtDuration(row.duration_ms)}</td>
                  <td className="px-3 py-2 text-gray-500">{fmtDate(row.started_at)}</td>
                  <td className="px-3 py-2 text-gray-500 max-w-[200px] truncate">
                    {row.error
                      ? <span className="text-red-400">{row.error}</span>
                      : <span>{summaryText(row) ?? "—"}</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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

      <PlatformHealthWidget />
      <DataHealthSection />
      <CoverageSection />
      <DataGapsSection />
      <StaleInstrumentsSection />
      <ProviderQuotaSection />
      <ProviderStatsSection />
      <SchedulerJobsSection />
      <CSVImportSection />
      <MarketBootstrapSection />
      <BootstrapSection />
      <AboutSection />
    </div>
  );
}
