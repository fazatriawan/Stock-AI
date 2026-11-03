import { type Recommendation } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { actionBadgeClass, confidenceColor } from "@/lib/utils";
import { AlertTriangle, CheckCircle, XCircle, Clock } from "lucide-react";

interface Props { recommendation: Recommendation }

const ACTION_ICONS = {
  BUY: CheckCircle,
  SELL: XCircle,
  HOLD: Clock,
  WAIT: Clock,
  INSUFFICIENT_DATA: AlertTriangle,
};

export function RecommendationCard({ recommendation: rec }: Props) {
  const ActionIcon = ACTION_ICONS[rec.action] ?? AlertTriangle;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Analisis Deterministik</CardTitle>
          {rec.urgency === "REVIEW_NOW" && (
            <Badge variant="danger">Tinjau Sekarang</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Action */}
        <div className="flex items-center gap-3">
          <ActionIcon size={20} className={actionBadgeClass(rec.action).split(" ")[1]} />
          <div>
            <span className={`text-lg font-bold px-2 py-0.5 rounded ${actionBadgeClass(rec.action)}`}>
              {rec.action}
            </span>
            <p className="text-xs text-gray-500 mt-0.5">Horizon: {rec.horizon}</p>
          </div>
          <div className="ml-auto text-right">
            <p className="text-xs text-gray-500">Confidence</p>
            <p className={`text-sm font-medium ${confidenceColor(rec.evidence_confidence)}`}>
              {rec.evidence_confidence}
            </p>
          </div>
        </div>

        {/* Hard gate */}
        {rec.hard_gate_status !== "PASS" && (
          <div className="rounded border border-red-800/40 bg-red-950/20 px-3 py-2">
            <p className="text-xs text-red-400 font-medium">{rec.hard_gate_status}</p>
            {rec.hard_gate_reason && (
              <p className="text-xs text-red-300/70 mt-0.5">{rec.hard_gate_reason}</p>
            )}
          </div>
        )}

        {/* Scores */}
        <div>
          <p className="text-xs text-gray-500 mb-2">Skor Per Pilar (0–100)</p>
          <div className="space-y-1.5">
            {(["fundamental", "valuation", "technical", "macro_policy", "risk_quality"] as const).map((factor) => {
              const score = rec.factor_scores[factor];
              return (
                <div key={factor} className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 w-28 capitalize">{factor.replace("_", " ")}</span>
                  {score !== null ? (
                    <>
                      <div className="flex-1 bg-gray-800 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${score >= 70 ? "bg-emerald-500" : score >= 50 ? "bg-amber-500" : "bg-red-500"}`}
                          style={{ width: `${score}%` }}
                        />
                      </div>
                      <span className={`text-xs w-8 text-right ${score >= 70 ? "text-emerald-400" : score >= 50 ? "text-amber-400" : "text-red-400"}`}>
                        {score.toFixed(0)}
                      </span>
                    </>
                  ) : (
                    <span className="text-xs text-gray-600">Data tidak tersedia</span>
                  )}
                </div>
              );
            })}
            <div className="flex items-center gap-2 pt-1 border-t border-gray-800">
              <span className="text-xs text-gray-400 font-medium w-28">Komposit</span>
              <div className="flex-1 bg-gray-800 rounded-full h-1.5">
                <div
                  className="h-1.5 rounded-full bg-blue-500"
                  style={{ width: `${rec.factor_scores.composite}%` }}
                />
              </div>
              <span className="text-xs text-blue-400 w-8 text-right font-medium">
                {rec.factor_scores.composite.toFixed(0)}
              </span>
            </div>
          </div>
        </div>

        {/* Bull thesis */}
        {rec.bull_thesis.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-1.5">Bull Case</p>
            <ul className="space-y-1">
              {rec.bull_thesis.map((point, i) => (
                <li key={i} className="flex gap-2 text-xs text-emerald-300/80">
                  <span className="text-emerald-500 mt-0.5">+</span>
                  {point}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Bear case */}
        {rec.bear_case.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-1.5">Bear Case</p>
            <ul className="space-y-1">
              {rec.bear_case.slice(0, 3).map((point, i) => (
                <li key={i} className="flex gap-2 text-xs text-red-300/80">
                  <span className="text-red-500 mt-0.5">−</span>
                  {point}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Data gaps */}
        {rec.data_gaps.length > 0 && (
          <div className="rounded border border-gray-700 bg-gray-800/40 px-3 py-2">
            <p className="text-xs text-gray-500 mb-1">Data tidak tersedia:</p>
            <div className="flex flex-wrap gap-1">
              {rec.data_gaps.map((gap) => (
                <Badge key={gap} variant="muted">{gap}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* AI enrichment */}
        {rec.ai_enriched && (
          <div className="border-t border-gray-800 pt-3 space-y-2">
            <p className="text-xs text-blue-400/70 font-medium">
              ✦ Diperkaya AI ({rec.ai_model ?? "claude"})
            </p>
            {rec.ai_macro_context && (
              <p className="text-xs text-gray-400">{rec.ai_macro_context}</p>
            )}
            {rec.ai_identified_risks.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">Risiko tambahan:</p>
                <ul className="space-y-0.5">
                  {rec.ai_identified_risks.map((r, i) => (
                    <li key={i} className="text-xs text-amber-300/70 flex gap-1.5">
                      <span className="text-amber-500">⚠</span>{r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Disclaimer */}
        <p className="text-xs text-gray-600 border-t border-gray-800 pt-2">
          {rec.disclaimer}
        </p>
      </CardContent>
    </Card>
  );
}
