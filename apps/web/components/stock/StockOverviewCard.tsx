import { type StockOverview } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatCurrency, formatPercent, formatDate } from "@/lib/utils";

interface Props { overview: StockOverview }

export function StockOverviewCard({ overview }: Props) {
  const { instrument: inst, last_price, last_price_date, price_provider, price_stale, technical } = overview;

  const ret1d = technical?.return_1d;
  const isPositive = ret1d !== null && ret1d !== undefined && ret1d > 0;
  const isNegative = ret1d !== null && ret1d !== undefined && ret1d < 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <CardTitle className="text-base">{inst.canonical_symbol}</CardTitle>
              <Badge variant="muted">{inst.exchange}</Badge>
              <Badge variant="muted">{inst.currency}</Badge>
            </div>
            {inst.company_name && (
              <p className="text-xs text-gray-500 mt-0.5">{inst.company_name}</p>
            )}
          </div>
          {price_stale && <Badge variant="warning">Data Lama</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Price */}
        <div>
          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-semibold text-gray-100">
              {last_price !== null ? formatCurrency(last_price, inst.currency) : "—"}
            </span>
            {ret1d !== null && ret1d !== undefined && (
              <span className={`text-sm font-medium ${isPositive ? "text-emerald-400" : isNegative ? "text-red-400" : "text-gray-400"}`}>
                {isPositive ? "+" : ""}{formatPercent(ret1d)}
              </span>
            )}
          </div>
          {last_price_date && (
            <p className="text-xs text-gray-500 mt-0.5">
              Harga per {last_price_date} · Sumber: {price_provider ?? "—"}
            </p>
          )}
        </div>

        {/* 52-week */}
        {technical && (
          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-gray-800">
            <Stat label="52W High" value={technical.high_52w !== null ? formatCurrency(technical.high_52w, inst.currency) : "N/A"} />
            <Stat label="52W Low" value={technical.low_52w !== null ? formatCurrency(technical.low_52w, inst.currency) : "N/A"} />
            <Stat label="Persentil 52W" value={technical.percentile_52w !== null ? formatPercent(technical.percentile_52w) : "N/A"} />
            <Stat label="Volume Ratio" value={technical.volume_ratio_20 !== null ? `${technical.volume_ratio_20.toFixed(2)}x` : "N/A"} />
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-gray-800">
          <Stat label="Sektor" value={inst.sector ?? "—"} />
          <Stat label="Industri" value={inst.industry ?? "—"} />
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm text-gray-200">{value}</p>
    </div>
  );
}
