"use client";

import { useEffect, useState } from "react";
import { api, type MarketStatus } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

export function MarketStatusGrid() {
  const [statuses, setStatuses] = useState<MarketStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.markets.status()
      .then(setStatuses)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[1, 2, 3].map((i) => (
          <Card key={i} className="animate-pulse">
            <CardContent className="py-4 h-20">{null}</CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {["IDX", "NYSE", "NASDAQ"].map((ex) => (
          <div key={ex} className="rounded-xl border border-gray-700/40 bg-gray-800/20 px-4 py-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-400">{ex}</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-700/50 text-slate-300">—</span>
            </div>
            <div className="flex items-center gap-1.5 mt-3">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-600" />
              <span className="text-xs text-slate-300">Backend tidak terhubung</span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (statuses.length === 0) {
    return <p className="text-sm text-slate-300">Tidak ada data status bursa.</p>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {statuses.map((s) => (
        <div key={s.exchange} className={`rounded-xl border px-4 py-4 space-y-2.5 ${
          s.is_trading_day
            ? "border-emerald-800/40 bg-emerald-950/10"
            : "border-gray-700/50 bg-gray-800/30"
        }`}>
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-gray-100">{s.exchange}</span>
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
              s.is_trading_day
                ? "bg-emerald-900/50 text-emerald-300 border-emerald-700/50"
                : "bg-gray-700/50 text-gray-400 border-gray-600/40"
            }`}>
              {s.is_trading_day ? "Hari Bursa" : "Libur"}
            </span>
          </div>
          <p className="text-xs text-slate-300">{s.timezone}</p>
          <div className="flex items-center gap-2 pt-0.5">
            <span className={`w-2 h-2 rounded-full ${s.is_eod_data_ready ? "bg-emerald-400" : "bg-amber-400"}`} />
            <span className="text-xs text-gray-300">
              {s.is_eod_data_ready ? "Data EOD tersedia" : "Menunggu EOD"}
            </span>
          </div>
          {s.session_date && (
            <p className="text-[11px] text-slate-300">Sesi: {s.session_date}</p>
          )}
        </div>
      ))}
    </div>
  );
}
