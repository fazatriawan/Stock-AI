"use client";

import { useState } from "react";
import { Search, DatabaseZap } from "lucide-react";
import { api, type StockOverview, type Recommendation, type InstrumentFreshness } from "@/lib/api";
import { StockOverviewCard } from "@/components/stock/StockOverviewCard";
import { RecommendationCard } from "@/components/stock/RecommendationCard";
import { TechnicalCard } from "@/components/stock/TechnicalCard";
import { FundamentalCard } from "@/components/stock/FundamentalCard";

function FreshnessChip({ freshness }: { freshness: InstrumentFreshness }) {
  const q = freshness.data_quality_pct;
  const isGood = q >= 95;
  const isMid = q >= 70 && q < 95;
  const color = isGood
    ? "text-emerald-400 border-emerald-800/40 bg-emerald-950/20"
    : isMid
    ? "text-amber-400 border-amber-800/40 bg-amber-950/20"
    : "text-red-400 border-red-800/40 bg-red-950/20";

  if (q >= 100) return null;  // semua FRESH — tidak perlu chip

  return (
    <div className={`inline-flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-lg border ${color}`}>
      <DatabaseZap size={11} />
      <span>Kualitas data: {q}%</span>
      {freshness.last_fresh_date && (
        <span className="opacity-70">· FRESH terakhir {freshness.last_fresh_date}</span>
      )}
    </div>
  );
}

export default function ExplorerPage() {
  const [query, setQuery] = useState("");
  const [overview, setOverview] = useState<StockOverview | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [freshness, setFreshness] = useState<InstrumentFreshness | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    await searchTicker(query.trim());
  }

  async function searchTicker(ticker: string) {
    if (!ticker) return;

    setLoading(true);
    setError(null);
    setOverview(null);
    setRecommendation(null);
    setFreshness(null);

    try {
      const [ov, rec] = await Promise.all([
        api.stocks.overview(ticker),
        api.stocks.analysis(ticker),
      ]);
      setOverview(ov);
      setRecommendation(rec);
      // Freshness best-effort — jangan blokir tampilan utama jika gagal
      api.data.freshness(ov.instrument.id)
        .then(setFreshness)
        .catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gagal memuat data");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Stock Explorer</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Cari ticker IDX (BBCA, BMRI) atau US (AAPL, MSFT) untuk melihat analisis
        </p>
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2 max-w-md">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={14} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Cari ticker: BBCA, IDX:BMRI, AAPL..."
            className="w-full pl-9 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-gray-500"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
        >
          {loading ? "Memuat..." : "Cari"}
        </button>
      </form>

      {/* Quick picks */}
      <div className="flex flex-wrap gap-2">
        {["BBCA", "BBRI", "BMRI", "TLKM", "AAPL", "MSFT", "NVDA"].map((sym) => (
          <button
            key={sym}
            onClick={() => {
              setQuery(sym);
              searchTicker(sym);
            }}
            className="px-2.5 py-1 bg-gray-800 hover:bg-gray-700 text-xs text-gray-400 hover:text-gray-200 rounded transition-colors border border-gray-700"
          >
            {sym}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3">
          <p className="text-sm text-red-400">{error}</p>
          <p className="text-xs text-gray-500 mt-1">
            Pastikan backend berjalan dan ticker ada di database (jalankan bootstrap terlebih dahulu).
          </p>
        </div>
      )}

      {/* Results */}
      {overview && (
        <div className="space-y-3">
          {freshness && <FreshnessChip freshness={freshness} />}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <StockOverviewCard overview={overview} />
            {recommendation && <RecommendationCard recommendation={recommendation} />}
            {overview.technical && <TechnicalCard technical={overview.technical} />}
            {overview.fundamental && <FundamentalCard fundamental={overview.fundamental} />}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!overview && !loading && !error && (
        <div className="text-center py-20 text-gray-600">
          <Search size={32} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">Masukkan ticker untuk melihat analisis</p>
          <p className="text-xs mt-1">Contoh: BBCA, BMRI.JK, AAPL</p>
        </div>
      )}
    </div>
  );
}
