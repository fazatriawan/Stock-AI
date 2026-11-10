"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Menu, X, ChevronDown,
  LayoutDashboard, Briefcase, Search, Target, Star, Database,
  Filter, Bell, Upload, Link2, Activity, Layers, TrendingDown,
  Sliders, CalendarDays, Globe, BookOpen, BookMarked, BarChart2,
} from "lucide-react";

const CORE_ITEMS = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portofolio", icon: Briefcase },
  { href: "/explorer", label: "Cari Saham", icon: Search },
  { href: "/decisions", label: "Rekomendasi", icon: Target },
  { href: "/watchlist", label: "Daftar Pantau", icon: Star },
  { href: "/settings", label: "Pengaturan", icon: Database },
];

const ADVANCED_ITEMS = [
  { href: "/screener", label: "Screener", icon: Filter },
  { href: "/alerts", label: "Alert Rules", icon: Bell },
  { href: "/portfolio/import", label: "Import Transaksi", icon: Upload },
  { href: "/portfolio/broker", label: "Broker Connections", icon: Link2 },
  { href: "/portfolio/health", label: "Portfolio Health", icon: Activity },
  { href: "/portfolio/positions", label: "Position Intelligence", icon: Layers },
  { href: "/portfolio/loss", label: "Loss Analyzer", icon: TrendingDown },
  { href: "/portfolio/rebalance", label: "Rebalance", icon: Sliders },
  { href: "/daily", label: "Daily Intelligence", icon: CalendarDays },
  { href: "/macro", label: "Macro & Policy", icon: Globe },
  { href: "/notebook", label: "Research Notebook", icon: BookOpen },
  { href: "/journal", label: "Decision Journal", icon: BookMarked },
  { href: "/performance", label: "Performance Lab", icon: BarChart2 },
];

const ALL_ITEMS = [...CORE_ITEMS, ...ADVANCED_ITEMS];

export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const currentPage = ALL_ITEMS.find(
    item => pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href))
  );

  function isActive(href: string) {
    return pathname === href || (href !== "/" && pathname.startsWith(href));
  }

  return (
    <>
      {/* Topbar — hanya di mobile */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 h-14 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-100">Stock Intelligence</span>
          {currentPage && (
            <span className="text-xs text-gray-500">· {currentPage.label}</span>
          )}
        </div>
        <button
          onClick={() => setOpen(true)}
          className="text-gray-400 hover:text-gray-200 p-1"
          aria-label="Buka menu"
        >
          <Menu size={20} />
        </button>
      </div>

      {/* Spacer di bawah topbar */}
      <div className="md:hidden h-14 shrink-0" />

      {/* Drawer overlay */}
      {open && (
        <div
          className="fixed inset-0 z-50 md:hidden"
          onClick={() => setOpen(false)}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

          {/* Drawer panel */}
          <div
            className="absolute left-0 top-0 bottom-0 w-64 bg-gray-900 border-r border-gray-800 flex flex-col overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-4 border-b border-gray-800">
              <div>
                <span className="text-sm font-semibold text-gray-100">Stock Intelligence</span>
                <p className="text-xs text-gray-500">IDX · US</p>
              </div>
              <button onClick={() => setOpen(false)} className="text-gray-500 hover:text-gray-300">
                <X size={18} />
              </button>
            </div>

            {/* Nav */}
            <nav className="flex-1 py-3">
              {/* Core items */}
              <div className="space-y-0.5 px-2">
                {CORE_ITEMS.map(({ href, label, icon: Icon }) => (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "flex items-center gap-2.5 px-3 py-2.5 rounded-md text-sm transition-colors",
                      isActive(href)
                        ? "bg-gray-800 text-white font-medium"
                        : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
                    )}
                  >
                    <Icon size={15} strokeWidth={1.75} />
                    {label}
                  </Link>
                ))}
              </div>

              {/* Advanced toggle */}
              <div className="mt-2 px-2">
                <button
                  onClick={() => setAdvancedOpen(o => !o)}
                  className="w-full flex items-center justify-between px-3 py-1.5 rounded-md text-xs text-gray-600 hover:text-gray-400 hover:bg-gray-800/40 transition-colors"
                >
                  <span className="uppercase tracking-wider font-semibold">Fitur Lanjutan</span>
                  <ChevronDown size={12} className={cn("transition-transform duration-200", advancedOpen && "rotate-180")} />
                </button>

                {advancedOpen && (
                  <div className="mt-1 space-y-0.5">
                    {ADVANCED_ITEMS.map(({ href, label, icon: Icon }) => (
                      <Link
                        key={href}
                        href={href}
                        onClick={() => setOpen(false)}
                        className={cn(
                          "flex items-center gap-2.5 px-3 py-2.5 rounded-md text-sm transition-colors",
                          isActive(href)
                            ? "bg-gray-800 text-white font-medium"
                            : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
                        )}
                      >
                        <Icon size={15} strokeWidth={1.75} />
                        {label}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </nav>

            <div className="px-4 py-3 border-t border-gray-800">
              <p className="text-xs text-gray-600">Riset pribadi — bukan nasihat investasi</p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
