import { type FundamentalSnapshot } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatPercent, formatCurrency } from "@/lib/utils";

interface Props { fundamental: FundamentalSnapshot }

function MetricRow({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex justify-between items-baseline py-1.5 border-b border-gray-800/50 last:border-0">
      <div>
        <span className="text-xs text-gray-500">{label}</span>
        {note && <span className="text-xs text-gray-600 ml-1">({note})</span>}
      </div>
      <span className="text-sm text-gray-200 font-medium">{value}</span>
    </div>
  );
}

const freshnessBadge = (f: string): "success" | "warning" | "danger" | "muted" =>
  ({ FRESH: "success", ACCEPTABLE: "warning", STALE: "danger" }[f] as any) ?? "muted";

export function FundamentalCard({ fundamental: f }: Props) {
  const isBank = f.sector === "Financials";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Fundamental</CardTitle>
          <div className="flex gap-1.5">
            <Badge variant={freshnessBadge(f.data_freshness)}>{f.data_freshness}</Badge>
            {f.period_end && <Badge variant="muted">{f.period_end}</Badge>}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isBank ? (
          <>
            <p className="text-xs text-gray-600 mb-2">Metrik Bank</p>
            {f.roe !== null && <MetricRow label="ROE" value={formatPercent(f.roe)} />}
            {f.nim !== null && <MetricRow label="NIM" value={formatPercent(f.nim)} />}
            {f.npl_gross !== null && <MetricRow label="NPL Gross" value={formatPercent(f.npl_gross)} />}
            {f.car !== null && <MetricRow label="CAR" value={formatPercent(f.car)} />}
            {f.pb_ratio !== null && <MetricRow label="P/B" value={`${f.pb_ratio.toFixed(2)}x`} />}
          </>
        ) : (
          <>
            {f.pe_ratio !== null && <MetricRow label="P/E" value={`${f.pe_ratio.toFixed(2)}x`} />}
            {f.pb_ratio !== null && <MetricRow label="P/B" value={`${f.pb_ratio.toFixed(2)}x`} />}
            {f.roe !== null && <MetricRow label="ROE" value={formatPercent(f.roe)} />}
            {f.eps !== null && <MetricRow label="EPS" value={f.eps.toLocaleString("id-ID", {maximumFractionDigits: 2})} />}
            {f.dividend_yield !== null && <MetricRow label="Dividend Yield" value={formatPercent(f.dividend_yield)} />}
          </>
        )}

        {f.metrics_missing.length > 0 && (
          <div className="mt-3 pt-2 border-t border-gray-800">
            <p className="text-xs text-gray-600 mb-1">Metrik tidak tersedia:</p>
            <div className="flex flex-wrap gap-1">
              {f.metrics_missing.map((m) => <Badge key={m} variant="muted">{m}</Badge>)}
            </div>
          </div>
        )}

        <p className="text-xs text-gray-600 mt-3 pt-2 border-t border-gray-800">
          {f.metrics_available.length} metrik fundamental tersedia
        </p>
      </CardContent>
    </Card>
  );
}
