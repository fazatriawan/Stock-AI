"use client";

import { useEffect, useState } from "react";
import { api, type PortfolioSummary, type Position } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TrendingUp, TrendingDown, RefreshCw, AlertTriangle, PlusCircle, Zap, Trash2, CloudDownload, Pencil } from "lucide-react";
import { AddTradeModal } from "@/components/portfolio/AddTradeModal";
import { QuickPositionModal } from "@/components/portfolio/QuickPositionModal";
import { EditPositionModal } from "@/components/portfolio/EditPositionModal";
import { ErrorDisplay } from "@/components/ui/ErrorDisplay";

function PnlBadge({ value, pct }: { value: number | null; pct: number | null }) {
  if (value === null || pct === null) return <span className="text-gray-500">N/A</span>;
  const isPositive = value >= 0;
  const Icon = isPositive ? TrendingUp : TrendingDown;
  return (
    <span className={`flex items-center gap-1 ${isPositive ? "text-emerald-400" : "text-red-400"}`}>
      <Icon size={14} />
      {formatCurrency(value)} ({formatPercent(pct)})
    </span>
  );
}

function SummaryCard({ title, value, sub }: { title: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="pt-4 pb-4">
        <p className="text-xs text-gray-500 mb-1">{title}</p>
        <div className="text-lg font-semibold text-gray-100">{value}</div>
        {sub && <div className="text-xs mt-0.5">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function PositionRow({
  pos,
  onDelete,
  onEdit,
}: {
  pos: Position;
  onDelete: (symbol: string) => void;
  onEdit: (pos: Position) => void;
}) {
  const hasMV = pos.market_value !== null;
  const isPos = (pos.unrealized_pnl ?? 0) >= 0;
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="border-b border-gray-800 hover:bg-gray-800/30 transition-colors group">
      <td className="py-3 px-4">
        <div className="font-medium text-gray-100 text-sm">{pos.canonical_symbol.split(":")[1] ?? pos.canonical_symbol}</div>
        {pos.company_name && <div className="text-xs text-gray-500 truncate max-w-[140px]">{pos.company_name}</div>}
      </td>
      <td className="py-3 px-4 text-right text-sm text-gray-300">
        {pos.lots.toFixed(0)} lot
        <div className="text-xs text-gray-600">{pos.shares.toLocaleString("id-ID")} saham</div>
      </td>
      <td className="py-3 px-4 text-right text-sm text-gray-300">
        {formatCurrency(pos.avg_cost)}
      </td>
      <td className="py-3 px-4 text-right text-sm text-gray-300">
        {pos.current_price !== null ? formatCurrency(pos.current_price) : <span className="text-gray-600">—</span>}
        {pos.current_price_date && (
          <div className="text-xs text-gray-600">{pos.current_price_date}</div>
        )}
      </td>
      <td className="py-3 px-4 text-right text-sm">
        {hasMV ? formatCurrency(pos.market_value) : <span className="text-gray-600">—</span>}
      </td>
      <td className="py-3 px-4 text-right text-sm">
        {pos.unrealized_pnl !== null ? (
          <div className={isPos ? "text-emerald-400" : "text-red-400"}>
            {isPos ? "+" : ""}{formatCurrency(pos.unrealized_pnl)}
            <div className="text-xs">
              {isPos ? "+" : ""}{formatPercent(pos.unrealized_pnl_pct)}
            </div>
          </div>
        ) : <span className="text-gray-600">—</span>}
      </td>
      <td className="py-3 px-4 text-right text-xs text-gray-500">
        {pos.weight > 0 ? `${(pos.weight * 100).toFixed(1)}%` : "—"}
      </td>
      <td className="py-3 px-4 text-right">
        {confirmDelete ? (
          <span className="flex items-center gap-1 justify-end">
            <button
              onClick={() => onDelete(pos.canonical_symbol)}
              className="text-xs text-red-400 hover:text-red-300 font-medium"
            >
              Hapus
            </button>
            <span className="text-gray-700">·</span>
            <button
              onClick={() => setConfirmDelete(false)}
              className="text-xs text-gray-500 hover:text-gray-300"
            >
              Batal
            </button>
          </span>
        ) : (
          <span className="flex items-center gap-1.5 justify-end opacity-0 group-hover:opacity-100 transition-all">
            <button
              onClick={() => onEdit(pos)}
              className="text-gray-600 hover:text-blue-400 transition-colors"
              title="Edit posisi"
            >
              <Pencil size={13} />
            </button>
            <button
              onClick={() => setConfirmDelete(true)}
              className="text-gray-600 hover:text-red-400 transition-colors"
              title="Hapus posisi"
            >
              <Trash2 size={13} />
            </button>
          </span>
        )}
      </td>
    </tr>
  );
}

export default function PortfolioPage() {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddTrade, setShowAddTrade] = useState(false);
  const [showQuickAdd, setShowQuickAdd] = useState(false);
  const [editingPosition, setEditingPosition] = useState<Position | null>(null);
  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);

  async function load() {
    try {
      setLoading(true);
      setError(null);
      const summary = await api.portfolio.summary();
      setData(summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat portofolio");
    } finally {
      setLoading(false);
    }
  }

  async function handleSeed() {
    try {
      await api.portfolio.seed();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Seed gagal");
    }
  }

  async function handleRefreshPrices() {
    setRefreshingPrices(true);
    setRefreshMsg(null);
    try {
      const r = await api.portfolio.refreshPrices();
      setRefreshMsg(`Refresh dimulai untuk ${r.triggered} saham. Harga terbaru akan muncul dalam beberapa detik.`);
      // Reload data setelah delay singkat
      setTimeout(() => load(), 3000);
    } catch (e) {
      setRefreshMsg("Gagal memulai refresh harga. Coba lagi.");
    } finally {
      setRefreshingPrices(false);
    }
  }

  async function handleDeletePosition(symbol: string) {
    try {
      await api.portfolio.deletePosition(symbol);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menghapus posisi");
    }
  }

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-6 w-40 bg-gray-800 rounded animate-pulse" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 bg-gray-800 rounded-lg animate-pulse" />
          ))}
        </div>
        <div className="h-64 bg-gray-800 rounded-lg animate-pulse" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 max-w-lg">
        <h1 className="text-lg font-semibold text-gray-100 mb-4">My Portfolio</h1>
        <ErrorDisplay error={error} onRetry={load} context="portofolio" />
      </div>
    );
  }

  const isEmpty = !data || data.positions.length === 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">My Portfolio</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            {data?.portfolio_name ?? "Default"} · {data?.base_currency ?? "IDR"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} className="gap-1.5" title="Muat ulang data portofolio">
            <RefreshCw size={13} />
            Muat Ulang
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefreshPrices}
            disabled={refreshingPrices}
            className="gap-1.5 border-blue-700/50 text-blue-400 hover:bg-blue-900/30"
            title="Ambil harga terkini dari provider data"
          >
            <CloudDownload size={13} className={refreshingPrices ? "animate-pulse" : ""} />
            {refreshingPrices ? "Memperbarui..." : "Refresh Harga"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowQuickAdd(true)}
            className="gap-1.5 border-emerald-700/50 text-emerald-400 hover:bg-emerald-900/30"
          >
            <Zap size={13} />
            Tambah Posisi
          </Button>
          <Button size="sm" onClick={() => setShowAddTrade(true)} className="gap-1.5">
            <PlusCircle size={13} />
            Tambah Trade
          </Button>
        </div>
      </div>

      {/* Refresh price feedback */}
      {refreshMsg && (
        <div className="rounded-lg border border-blue-800/40 bg-blue-950/15 px-4 py-2.5 flex items-center justify-between gap-3">
          <p className="text-xs text-blue-400">{refreshMsg}</p>
          <button onClick={() => setRefreshMsg(null)} className="text-blue-400/40 hover:text-blue-400/80 text-xs shrink-0">✕</button>
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard
          title="Total Diinvestasikan"
          value={formatCurrency(data?.total_invested ?? 0)}
        />
        <SummaryCard
          title="Nilai Pasar"
          value={formatCurrency(data?.market_value ?? 0)}
          sub={data && data.market_value > 0 ? (
            <span className="text-gray-500 text-xs">{data.trade_count} transaksi</span>
          ) : null}
        />
        <SummaryCard
          title="Unrealized P/L"
          value={
            <PnlBadge
              value={data?.unrealized_pnl ?? null}
              pct={data?.unrealized_pnl_pct ?? null}
            />
          }
        />
        <SummaryCard
          title="Jumlah Posisi"
          value={data?.positions.length ?? 0}
          sub={
            data?.concentration_warnings.length ? (
              <span className="text-amber-400 text-xs flex items-center gap-1">
                <AlertTriangle size={11} />
                {data.concentration_warnings.length} peringatan
              </span>
            ) : null
          }
        />
      </div>

      {/* Concentration warnings */}
      {data?.concentration_warnings.length ? (
        <div className="rounded border border-amber-800/40 bg-amber-950/20 px-4 py-3 space-y-1">
          <p className="text-xs font-medium text-amber-400">Peringatan Konsentrasi</p>
          {data.concentration_warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-300/70">⚠ {w}</p>
          ))}
        </div>
      ) : null}

      {/* Empty state */}
      {isEmpty ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-gray-400 mb-2">Portofolio masih kosong.</p>
            <p className="text-xs text-gray-600 mb-4">
              Muat data awal (BMRI, BBRI, BBNI, BBCA) dari CR §10 atau tambah trade manual.
            </p>
            <div className="flex justify-center gap-3">
              <Button size="sm" onClick={handleSeed}>
                Muat Data Awal
              </Button>
              <Button size="sm" variant="outline" onClick={() => setShowAddTrade(true)}>
                Tambah Trade Manual
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Positions table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Posisi Aktif</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 text-xs text-gray-500">
                      <th className="py-2.5 px-4 text-left">Saham</th>
                      <th className="py-2.5 px-4 text-right">Lot / Saham</th>
                      <th className="py-2.5 px-4 text-right">Avg Cost</th>
                      <th className="py-2.5 px-4 text-right">Harga Terakhir</th>
                      <th className="py-2.5 px-4 text-right">Nilai Pasar</th>
                      <th className="py-2.5 px-4 text-right">Unrealized P/L</th>
                      <th className="py-2.5 px-4 text-right">Bobot</th>
                      <th className="py-2.5 px-4 text-right w-10"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.positions.map((pos) => (
                      <PositionRow key={pos.instrument_id} pos={pos} onDelete={handleDeletePosition} onEdit={setEditingPosition} />
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Sector allocation */}
          {Object.keys(data.sector_weights).length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Alokasi Sektor</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(data.sector_weights)
                  .sort(([, a], [, b]) => b - a)
                  .map(([sector, weight]) => (
                    <div key={sector} className="flex items-center gap-3">
                      <span className="text-xs text-gray-400 w-32 truncate">{sector}</span>
                      <div className="flex-1 bg-gray-800 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${weight > 0.5 ? "bg-amber-500" : "bg-blue-500"}`}
                          style={{ width: `${weight * 100}%` }}
                        />
                      </div>
                      <span className={`text-xs w-10 text-right ${weight > 0.5 ? "text-amber-400" : "text-gray-400"}`}>
                        {(weight * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))}
              </CardContent>
            </Card>
          )}
        </>
      )}

      <p className="text-xs text-gray-600">
        Data ini hanya untuk riset pribadi, bukan nasihat investasi.
        Keputusan transaksi sepenuhnya menjadi tanggung jawab pengguna.
      </p>

      {showQuickAdd && (
        <QuickPositionModal
          onClose={() => setShowQuickAdd(false)}
          onSuccess={() => { setShowQuickAdd(false); load(); }}
        />
      )}

      {editingPosition && (
        <EditPositionModal
          position={editingPosition}
          onClose={() => setEditingPosition(null)}
          onSuccess={() => { setEditingPosition(null); load(); }}
        />
      )}

      {showAddTrade && (
        <AddTradeModal
          onClose={() => setShowAddTrade(false)}
          onSuccess={() => { setShowAddTrade(false); load(); }}
        />
      )}
    </div>
  );
}
