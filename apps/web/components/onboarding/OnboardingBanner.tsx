"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { CheckCircle, Circle, ChevronRight, X, Database, Briefcase, TrendingUp } from "lucide-react";

const STORAGE_KEY = "si_onboarding_dismissed";

interface Step {
  id: string;
  icon: React.ElementType;
  title: string;
  desc: string;
  href: string;
  cta: string;
  check: () => Promise<boolean>;
}

const STEPS: Step[] = [
  {
    id: "data",
    icon: Database,
    title: "Muat data pasar",
    desc: "Bootstrap instrumen IDX + harga historis dari yfinance",
    href: "/settings",
    cta: "Buka Setup",
    check: async () => {
      try {
        const s = await api.admin.setupStatus();
        return s.is_ready;
      } catch { return false; }
    },
  },
  {
    id: "portfolio",
    icon: Briefcase,
    title: "Tambah posisi saham",
    desc: "Masukkan saham yang kamu pegang via \"Tambah Posisi\"",
    href: "/portfolio",
    cta: "Buka Portofolio",
    check: async () => {
      try {
        const s = await api.portfolio.summary();
        return (s.positions?.length ?? 0) > 0;
      } catch { return false; }
    },
  },
  {
    id: "explore",
    icon: TrendingUp,
    title: "Jelajahi analisis",
    desc: "Lihat Decision Center, Screener, atau Daily Intelligence",
    href: "/decisions",
    cta: "Mulai Eksplorasi",
    check: async () => false, // selalu tampil sebagai langkah terakhir
  },
];

export function OnboardingBanner() {
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [dismissed, setDismissed] = useState(true); // start hidden, reveal after check
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem(STORAGE_KEY)) {
      setDismissed(true);
      setLoading(false);
      return;
    }

    Promise.all(STEPS.map(async (s) => [s.id, await s.check()] as [string, boolean]))
      .then((results) => {
        const map = Object.fromEntries(results);
        setDone(map);
        // Sembunyikan jika semua langkah wajib selesai (data + portfolio)
        const allDone = map["data"] && map["portfolio"];
        if (allDone) {
          localStorage.setItem(STORAGE_KEY, "1");
          setDismissed(true);
        } else {
          setDismissed(false);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  function dismiss() {
    localStorage.setItem(STORAGE_KEY, "1");
    setDismissed(true);
  }

  if (loading || dismissed) return null;

  const completedCount = STEPS.filter((s) => done[s.id]).length;

  return (
    <div className="rounded-xl border border-blue-700/30 bg-gradient-to-br from-blue-950/30 to-blue-900/10 p-5 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-semibold text-blue-200">Selamat datang di Stock Intelligence</p>
          <p className="text-xs text-blue-400/80 mt-0.5">
            Selesaikan {STEPS.length} langkah berikut untuk mulai · {completedCount}/{STEPS.length} selesai
          </p>
        </div>
        <button
          onClick={dismiss}
          className="text-blue-400/50 hover:text-blue-300 transition-colors ml-3 shrink-0 p-1 rounded hover:bg-blue-900/30"
          title="Sembunyikan panduan"
        >
          <X size={13} />
        </button>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-blue-900/50 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500 rounded-full transition-all duration-500"
          style={{ width: `${(completedCount / STEPS.length) * 100}%` }}
        />
      </div>

      {/* Steps */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
        {STEPS.map((step, i) => {
          const isDone = done[step.id];
          const Icon = step.icon;
          return (
            <div
              key={step.id}
              className={`rounded-lg p-3.5 border transition-colors ${
                isDone
                  ? "border-emerald-700/40 bg-emerald-950/20"
                  : "border-blue-700/30 bg-blue-950/20 hover:bg-blue-950/30"
              }`}
            >
              <div className="flex items-start gap-2.5">
                <div className="mt-0.5 shrink-0">
                  {isDone
                    ? <CheckCircle size={15} className="text-emerald-400" />
                    : <Circle size={15} className="text-blue-500/60" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-xs font-semibold ${isDone ? "text-emerald-400/70 line-through" : "text-blue-100"}`}>
                    {i + 1}. {step.title}
                  </p>
                  <p className="text-xs text-blue-300/60 mt-1 leading-relaxed">{step.desc}</p>
                  {!isDone && (
                    <Link
                      href={step.href}
                      className="inline-flex items-center gap-1 mt-2.5 text-xs text-blue-400 hover:text-blue-200 font-medium transition-colors"
                    >
                      {step.cta} <ChevronRight size={10} />
                    </Link>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
