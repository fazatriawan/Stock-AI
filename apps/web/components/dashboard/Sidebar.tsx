"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Briefcase,
  Search,
  Target,
  Star,
  Database,
  ChevronDown,
  Filter,
  Bell,
  Upload,
  Link2,
  Activity,
  Layers,
  TrendingDown,
  Sliders,
  CalendarDays,
  Globe,
  BookOpen,
  BookMarked,
  BarChart2,
} from "lucide-react";

// 6 item inti — selalu tampil
const CORE_ITEMS = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portofolio", icon: Briefcase },
  { href: "/explorer", label: "Cari Saham", icon: Search },
  { href: "/decisions", label: "Rekomendasi", icon: Target },
  { href: "/watchlist", label: "Daftar Pantau", icon: Star },
  { href: "/settings", label: "Pengaturan", icon: Database },
];

// Item lanjutan — collapse by default
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

const STORAGE_KEY = "si_sidebar_advanced";

export function Sidebar() {
  const pathname = usePathname();
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // Buka otomatis jika halaman aktif ada di advanced list
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "1") {
      setAdvancedOpen(true);
      return;
    }
    const isAdvancedActive = ADVANCED_ITEMS.some(
      (item) => pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href))
    );
    if (isAdvancedActive) setAdvancedOpen(true);
  }, [pathname]);

  function toggleAdvanced() {
    const next = !advancedOpen;
    setAdvancedOpen(next);
    localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
  }

  function isActive(href: string) {
    return pathname === href || (href !== "/" && pathname.startsWith(href));
  }

  return (
    <aside className="w-52 bg-gray-900 border-r border-gray-800 flex flex-col min-h-screen sticky top-0">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-gray-800">
        <span className="text-sm font-semibold text-gray-100 tracking-tight">Stock Intelligence</span>
        <p className="text-xs text-gray-500 mt-0.5">IDX · US</p>
      </div>

      <nav className="flex-1 py-3 overflow-y-auto">
        {/* Core items */}
        <div className="space-y-0.5 px-2">
          {CORE_ITEMS.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors",
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
            onClick={toggleAdvanced}
            className="w-full flex items-center justify-between px-3 py-1.5 rounded-md text-xs text-gray-600 hover:text-gray-400 hover:bg-gray-800/40 transition-colors"
          >
            <span className="uppercase tracking-wider font-semibold">Fitur Lanjutan</span>
            <ChevronDown
              size={12}
              className={cn("transition-transform duration-200", advancedOpen && "rotate-180")}
            />
          </button>

          {advancedOpen && (
            <div className="mt-1 space-y-0.5">
              {ADVANCED_ITEMS.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors",
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
    </aside>
  );
}
