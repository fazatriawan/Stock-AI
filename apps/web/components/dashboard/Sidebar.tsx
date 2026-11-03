"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Briefcase,
  Search,
  Filter,
  Target,
  Globe,
  BookOpen,
  BarChart2,
  Database,
  Upload,
  Link2,
  Activity,
  Layers,
  TrendingDown,
  Sliders,
  CalendarDays,
  BookMarked,
} from "lucide-react";

const navGroups = [
  {
    label: "Utama",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard },
      { href: "/explorer", label: "Stock Explorer", icon: Search },
      { href: "/screener", label: "Screener", icon: Filter },
      { href: "/decisions", label: "Decision Center", icon: Target },
    ],
  },
  {
    label: "Portofolio",
    items: [
      { href: "/portfolio", label: "My Portfolio", icon: Briefcase },
      { href: "/portfolio/import", label: "Import Transaksi", icon: Upload },
      { href: "/portfolio/broker", label: "Broker Connections", icon: Link2 },
      { href: "/portfolio/health", label: "Portfolio Health", icon: Activity },
    ],
  },
  {
    label: "Analisis",
    items: [
      { href: "/portfolio/positions", label: "Position Intelligence", icon: Layers },
      { href: "/portfolio/loss", label: "Loss Analyzer", icon: TrendingDown },
      { href: "/portfolio/rebalance", label: "Rebalance Simulator", icon: Sliders },
    ],
  },
  {
    label: "Riset",
    items: [
      { href: "/daily", label: "Daily Intelligence", icon: CalendarDays },
      { href: "/macro", label: "Macro & Policy", icon: Globe },
      { href: "/notebook", label: "Research Notebook", icon: BookOpen },
      { href: "/journal", label: "Decision Journal", icon: BookMarked },
    ],
  },
  {
    label: "Lab",
    items: [
      { href: "/performance", label: "Performance Lab", icon: BarChart2 },
      { href: "/settings", label: "Data & Settings", icon: Database },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col min-h-screen sticky top-0">
      <div className="px-4 py-5 border-b border-gray-800">
        <span className="text-sm font-semibold text-gray-100 tracking-tight">Stock Intelligence</span>
        <p className="text-xs text-gray-500 mt-0.5">IDX · US</p>
      </div>
      <nav className="flex-1 py-3 overflow-y-auto">
        {navGroups.map((group) => (
          <div key={group.label} className="mb-1">
            <p className="px-4 py-1.5 text-[10px] font-semibold text-gray-600 uppercase tracking-wider">
              {group.label}
            </p>
            <div className="space-y-0.5 px-2">
              {group.items.map(({ href, label, icon: Icon }) => {
                const isActive = pathname === href || (href !== "/" && pathname.startsWith(href));
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors",
                      isActive
                        ? "bg-gray-800 text-white font-medium"
                        : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
                    )}
                  >
                    <Icon size={15} strokeWidth={1.75} />
                    {label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="px-4 py-3 border-t border-gray-800">
        <p className="text-xs text-gray-600">
          Riset pribadi — bukan nasihat investasi
        </p>
      </div>
    </aside>
  );
}
