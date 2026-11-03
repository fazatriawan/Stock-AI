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
      <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3">
        <p className="text-xs text-red-400">Gagal memuat status bursa: {error}</p>
        <p className="text-xs text-gray-500 mt-1">Pastikan backend API berjalan di localhost:8000</p>
      </div>
    );
  }

  if (statuses.length === 0) {
    return <p className="text-sm text-gray-500">Tidak ada data status bursa.</p>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {statuses.map((s) => (
        <Card key={s.exchange}>
          <CardContent className="py-4 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-200">{s.exchange}</span>
              <Badge variant={s.is_trading_day ? "success" : "muted"}>
                {s.is_trading_day ? "Hari Bursa" : "Libur"}
              </Badge>
            </div>
            <p className="text-xs text-gray-500">{s.timezone}</p>
            <div className="flex items-center gap-2 mt-1">
              <span
                className={`w-1.5 h-1.5 rounded-full ${s.is_eod_data_ready ? "bg-emerald-400" : "bg-amber-400"}`}
              />
              <span className="text-xs text-gray-400">
                {s.is_eod_data_ready ? "Data EOD tersedia" : "Menunggu EOD"}
              </span>
            </div>
            <p className="text-xs text-gray-600">Sesi: {s.session_date}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
