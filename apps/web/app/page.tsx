"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type PortfolioSummary, type DailyIntelligence } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { MarketStatusGrid } from "@/components/dashboard/MarketStatusGrid";
import { DataHealthStatus } from "@/components/dashboard/DataHealthStatus";
import { TrendingUp, TrendingDown, AlertTriangle, ChevronRight, Target } from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function PnlColor(pct: number) {
  return pct >= 0 ? "text-emerald-400" : "text-red-400";
}

function KpiCard({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: "green" | "red" | "neutral";
}) {
  const valueColor =
    highlight === "green" ? "text-emerald-400"
    : highlight === "red" ? "text-red-400"
    : "text-gray-100";
  return (
    <div className="bg-gray-800/40 border border-gray-700/40 rounded-xl p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-xl font-bold ${valueColor}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Portfolio KPIs
// ---------------------------------------------------------------------------
function PortfolioKpis() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [daily, setDaily] = useState<DailyIntelligence | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      api.portfolio.summary(),
      api.daily.intelligence(),
    ]).then(([p, d]) => {
      if (p.status === "fulfilled") setPortfolio(p.value);
      if (d.status === "fulfilled") setDaily(d.value);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-20 bg-gray-800 rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Total Portofolio" value="—" sub="Belum ada posisi" />
        <KpiCard label="Unrealized P/L" value="—" sub="vs harga beli rata-rata" />
        <KpiCard label="Posisi Aktif" value="—" sub="Tambah transaksi di Import" />
        <KpiCard label="Sektor" value="—" sub="Diversifikasi portofolio" />
      </div>
    );
  }

  const pnlPct = portfolio.unrealized_pnl_pct;
  const pnlSign = pnlPct >= 0 ? "+" : "";
  const positions = portfolio.positions?.length ?? 0;
  const sectors = Object.keys(portfolio.sector_weights ?? {}).length;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard
          label="Nilai Pasar"
          value={formatCurrency(portfolio.market_value)}
          sub={`Modal: ${formatCurrency(portfolio.total_invested)}`}
        />
        <KpiCard
          label="Unrealized P/L"
          value={`${pnlSign}${pnlPct.toFixed(2)}%`}
          sub={`${pnlSign}${formatCurrency(portfolio.unrealized_pnl)}`}
          highlight={pnlPct >= 0 ? "green" : "red"}
        />
        <KpiCard
          label="Posisi Aktif"
          value={String(positions)}
          sub={`${portfolio.trade_count} transaksi`}
        />
        <KpiCard
          label="Sektor"
          value={String(sectors)}
          sub="Diversifikasi aktif"
        />
      </div>

      {/* Alerts */}
      {(portfolio.concentration_warnings?.length > 0 || (daily?.alerts?.length ?? 0) > 0) && (
        <div className="space-y-1.5">
          {portfolio.concentration_warnings?.map((w, i) => (
            <div key={i} className="flex items-start gap-2 rounded-lg border border-amber-800/30 bg-amber-950/15 px-3 py-2">
              <AlertTriangle size={12} className="text-amber-400 mt-0.5 shrink-0" />
              <p className="text-xs text-amber-400/90">{w}</p>
            </div>
          ))}
          {daily?.alerts?.map((a, i) => (
            <div key={i} className="flex items-start gap-2 rounded-lg border border-blue-800/30 bg-blue-950/15 px-3 py-2">
              <AlertTriangle size={12} className="text-blue-400 mt-0.5 shrink-0" />
              <p className="text-xs text-blue-400/90">{a}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Top positions
// ---------------------------------------------------------------------------
function TopPositions() {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.portfolio.summary()
      .then(setPortfolio)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="h-24 bg-gray-800 rounded-xl animate-pulse" />;

  const positions = portfolio?.positions ?? [];
  if (positions.length === 0) return (
    <div className="text-center py-6 text-gray-600 text-sm">
      Belum ada posisi —{" "}
      <Link href="/portfolio/import" className="text-blue-400 hover:underline">import transaksi</Link>
    </div>
  );

  const sorted = [...positions].sort((a, b) => Math.abs(b.unrealized_pnl_pct ?? 0) - Math.abs(a.unrealized_pnl_pct ?? 0)).slice(0, 5);

  return (
    <div className="space-y-1.5">
      {sorted.map(pos => {
        const ticker = pos.canonical_symbol?.split(":")?.[1] ?? pos.canonical_symbol;
        const pct = pos.unrealized_pnl_pct ?? 0;
        const isUp = pct >= 0;
        return (
          <div key={pos.canonical_symbol} className="flex items-center gap-3 rounded-lg bg-gray-800/30 border border-gray-700/30 px-3 py-2.5">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-100">{ticker}</span>
                <span className="text-xs text-gray-500">{pos.sector ?? "—"}</span>
              </div>
              <p className="text-xs text-gray-600">{formatCurrency(pos.market_value ?? 0)}</p>
            </div>
            <div className="text-right">
              <span className={`text-sm font-medium ${PnlColor(pct)}`}>
                {isUp ? "+" : ""}{pct.toFixed(2)}%
              </span>
              <div className={`flex items-center justify-end gap-0.5 ${PnlColor(pct)}`}>
                {isUp ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
              </div>
            </div>
          </div>
        );
      })}
      <Link
        href="/portfolio"
        className="flex items-center justify-center gap-1 text-xs text-gray-500 hover:text-gray-300 py-1 transition-colors"
      >
        Lihat semua posisi <ChevronRight size={12} />
      </Link>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quick links
// ---------------------------------------------------------------------------
const QUICK_LINKS = [
  { href: "/decisions", label: "Decision Center", desc: "Sinyal beli/jual/tahan" },
  { href: "/screener", label: "Screener", desc: "Filter saham IDX & US" },
  { href: "/portfolio/rebalance", label: "Rebalance", desc: "Simulasi rebalancing" },
  { href: "/daily", label: "Daily Intelligence", desc: "Ringkasan hari ini" },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function OverviewPage() {
  return (
    <div className="p-6 space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Overview</h1>
        <p className="text-sm text-gray-500 mt-0.5">Ringkasan portofolio & market hari ini</p>
      </div>

      {/* Market status */}
      <section>
        <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Status Bursa</h2>
        <MarketStatusGrid />
      </section>

      {/* Portfolio KPIs */}
      <section>
        <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Portofolio</h2>
        <PortfolioKpis />
      </section>

      {/* Top positions */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Posisi Teratas</h2>
          <Link href="/portfolio/positions" className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1">
            Intelligence <ChevronRight size={11} />
          </Link>
        </div>
        <TopPositions />
      </section>

      {/* Quick links */}
      <section>
        <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Aksi Cepat</h2>
        <div className="grid grid-cols-2 gap-2">
          {QUICK_LINKS.map(link => (
            <Link
              key={link.href}
              href={link.href}
              className="bg-gray-800/30 border border-gray-700/30 hover:border-gray-600/50 rounded-xl px-4 py-3 flex items-center justify-between group transition-colors"
            >
              <div>
                <p className="text-sm font-medium text-gray-200 group-hover:text-white transition-colors">{link.label}</p>
                <p className="text-xs text-gray-600">{link.desc}</p>
              </div>
              <ChevronRight size={14} className="text-gray-600 group-hover:text-gray-400 transition-colors" />
            </Link>
          ))}
        </div>
      </section>

      {/* Data health */}
      <section>
        <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Status Provider Data</h2>
        <DataHealthStatus />
      </section>

      {/* Disclaimer */}
      <div className="rounded-lg border border-amber-800/40 bg-amber-950/20 px-4 py-3">
        <p className="text-xs text-amber-400/80">
          <strong>Catatan:</strong> Seluruh data yang ditampilkan saat ini adalah data sintetis untuk testing.
          Tidak ada angka yang mencerminkan kondisi pasar nyata. Sistem ini bukan nasihat investasi.
          Keputusan transaksi sepenuhnya menjadi tanggung jawab pengguna.
        </p>
      </div>
    </div>
  );
}
