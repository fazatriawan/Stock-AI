import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(
  value: number | null | undefined,
  options?: Intl.NumberFormatOptions & { fallback?: string }
): string {
  if (value === null || value === undefined) return options?.fallback ?? "N/A";
  return new Intl.NumberFormat("id-ID", options).format(value);
}

export function formatPercent(
  value: number | null | undefined,
  decimals = 2
): string {
  if (value === null || value === undefined) return "N/A";
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatCurrency(
  value: number | null | undefined,
  currency = "IDR"
): string {
  if (value === null || value === undefined) return "N/A";
  if (currency === "IDR") {
    if (value >= 1_000_000_000_000) return `Rp ${(value / 1_000_000_000_000).toFixed(2)}T`;
    if (value >= 1_000_000_000) return `Rp ${(value / 1_000_000_000).toFixed(2)}M`;
    if (value >= 1_000_000) return `Rp ${(value / 1_000_000).toFixed(2)}Jt`;
    return `Rp ${value.toLocaleString("id-ID")}`;
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    notation: "compact",
  }).format(value);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function actionColor(action: string): string {
  switch (action) {
    case "BUY": return "text-emerald-600 dark:text-emerald-400";
    case "SELL": return "text-red-600 dark:text-red-400";
    case "HOLD": return "text-blue-600 dark:text-blue-400";
    case "WAIT": return "text-amber-600 dark:text-amber-400";
    default: return "text-gray-500 dark:text-gray-400";
  }
}

export function actionBadgeClass(action: string): string {
  switch (action) {
    case "BUY": return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200";
    case "SELL": return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
    case "HOLD": return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
    case "WAIT": return "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200";
    default: return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
  }
}

export function confidenceColor(confidence: string): string {
  switch (confidence) {
    case "HIGH": return "text-emerald-600";
    case "MEDIUM": return "text-amber-600";
    case "LOW": return "text-red-600";
    default: return "text-gray-500";
  }
}

export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-gray-400";
  if (score >= 70) return "text-emerald-600";
  if (score >= 50) return "text-amber-600";
  return "text-red-600";
}
