"use client";

import { useEffect, useState } from "react";
import { api, type ProviderHealth } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";

const statusColor = (s: string) => ({
  OK: "text-emerald-400",
  DEGRADED: "text-amber-400",
  DOWN: "text-red-400",
  UNKNOWN: "text-gray-400",
}[s] ?? "text-gray-400");

export function DataHealthStatus() {
  const [providers, setProviders] = useState<ProviderHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.data.health()
      .then((d) => setProviders(d.providers))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-xs text-gray-500">Memeriksa provider...</div>;
  if (error) return <div className="text-xs text-red-400">Error: {error}</div>;

  return (
    <div className="flex flex-wrap gap-3">
      {providers.map((p) => (
        <Card key={p.provider} className="w-48">
          <CardContent className="py-3 space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-300 capitalize">{p.provider}</span>
              <span className={`text-xs font-semibold ${statusColor(p.status)}`}>{p.status}</span>
            </div>
            {p.notes && <p className="text-xs text-gray-600 truncate">{p.notes}</p>}
            {p.last_error && <p className="text-xs text-red-500 truncate">{p.last_error}</p>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
