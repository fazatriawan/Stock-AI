"use client";

import { AlertTriangle, RefreshCw, WifiOff, ServerCrash } from "lucide-react";

interface Props {
  error: string;
  onRetry?: () => void;
  context?: string; // mis. "portofolio", "data harga", "screener"
}

function categorize(msg: string): { icon: React.ElementType; friendly: string; hint: string } {
  const m = msg.toLowerCase();
  if (m.includes("network") || m.includes("fetch") || m.includes("failed to fetch") || m.includes("networkerror")) {
    return {
      icon: WifiOff,
      friendly: "Tidak bisa terhubung ke server",
      hint: "Periksa koneksi internet, lalu coba lagi.",
    };
  }
  if (m.includes("500") || m.includes("internal server")) {
    return {
      icon: ServerCrash,
      friendly: "Server sedang bermasalah",
      hint: "Backend mengalami error. Coba lagi dalam beberapa saat.",
    };
  }
  if (m.includes("404") || m.includes("not found")) {
    return {
      icon: AlertTriangle,
      friendly: "Data tidak ditemukan",
      hint: "Mungkin data belum dimuat. Coba buka Settings → Setup Data.",
    };
  }
  if (m.includes("401") || m.includes("403") || m.includes("unauthorized")) {
    return {
      icon: AlertTriangle,
      friendly: "Akses ditolak",
      hint: "Sesi mungkin kedaluwarsa. Muat ulang halaman.",
    };
  }
  return {
    icon: AlertTriangle,
    friendly: "Terjadi kesalahan",
    hint: "Coba lagi atau hubungi dukungan jika masalah berlanjut.",
  };
}

export function ErrorDisplay({ error, onRetry, context }: Props) {
  const { icon: Icon, friendly, hint } = categorize(error);
  return (
    <div className="rounded-xl border border-red-800/40 bg-red-950/15 px-4 py-4 space-y-2">
      <div className="flex items-center gap-2">
        <Icon size={15} className="text-red-400 shrink-0" />
        <p className="text-sm font-medium text-red-300">
          {context ? `Gagal memuat ${context}` : friendly}
        </p>
      </div>
      <p className="text-xs text-red-400/70 leading-relaxed">{hint}</p>
      {process.env.NODE_ENV === "development" && (
        <p className="text-[10px] text-red-500/50 font-mono break-all">{error}</p>
      )}
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-1.5 mt-1 text-xs text-red-400 hover:text-red-300 transition-colors"
        >
          <RefreshCw size={11} />
          Coba lagi
        </button>
      )}
    </div>
  );
}
