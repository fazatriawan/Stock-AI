import { type TechnicalSnapshot } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatPercent } from "@/lib/utils";

interface Props { technical: TechnicalSnapshot }

function Stat({ label, value, positive }: { label: string; value: string; positive?: boolean | null }) {
  const color = positive === true ? "text-emerald-400" : positive === false ? "text-red-400" : "text-gray-300";
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-sm font-medium ${color}`}>{value}</p>
    </div>
  );
}

export function TechnicalCard({ technical: t }: Props) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Technical</CardTitle>
          <Badge variant={t.sufficient_data ? "success" : "warning"}>
            {t.bars_available} bar
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-3">
          <Stat label="SMA 20" value={t.sma_20 !== null ? t.sma_20.toLocaleString("id-ID", {maximumFractionDigits: 2}) : "N/A"} positive={t.above_sma_20} />
          <Stat label="SMA 50" value={t.sma_50 !== null ? t.sma_50.toLocaleString("id-ID", {maximumFractionDigits: 2}) : "N/A"} positive={t.above_sma_50} />
          <Stat label="SMA 200" value={t.sma_200 !== null ? t.sma_200.toLocaleString("id-ID", {maximumFractionDigits: 2}) : "N/A"} positive={t.above_sma_200} />
        </div>

        <div className="grid grid-cols-3 gap-3 pt-2 border-t border-gray-800">
          <Stat label="RSI 14" value={t.rsi_14 !== null ? t.rsi_14.toFixed(1) : "N/A"} positive={t.rsi_14 !== null ? (t.rsi_14 < 70 && t.rsi_14 > 30) : null} />
          <Stat label="MACD" value={t.macd !== null ? t.macd.toFixed(2) : "N/A"} positive={t.macd !== null ? t.macd > 0 : null} />
          <Stat label="ATR 14" value={t.atr_14 !== null ? t.atr_14.toFixed(2) : "N/A"} />
        </div>

        <div className="grid grid-cols-3 gap-3 pt-2 border-t border-gray-800">
          <Stat label="Return 1D" value={t.return_1d !== null ? formatPercent(t.return_1d) : "N/A"} positive={t.return_1d !== null ? t.return_1d > 0 : null} />
          <Stat label="Return 5D" value={t.return_5d !== null ? formatPercent(t.return_5d) : "N/A"} positive={t.return_5d !== null ? t.return_5d > 0 : null} />
          <Stat label="Return 20D" value={t.return_20d !== null ? formatPercent(t.return_20d) : "N/A"} positive={t.return_20d !== null ? t.return_20d > 0 : null} />
        </div>

        {t.golden_cross !== null && (
          <div className="flex gap-2 pt-2 border-t border-gray-800">
            <Badge variant={t.golden_cross ? "success" : "danger"}>
              {t.golden_cross ? "Golden Cross" : "Death Cross"}
            </Badge>
            {t.above_sma_200 !== null && (
              <Badge variant={t.above_sma_200 ? "success" : "warning"}>
                {t.above_sma_200 ? "Di atas SMA200" : "Di bawah SMA200"}
              </Badge>
            )}
          </div>
        )}

        {t.missing_indicators.length > 0 && (
          <p className="text-xs text-gray-600">
            Indikator belum cukup data: {t.missing_indicators.join(", ")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
