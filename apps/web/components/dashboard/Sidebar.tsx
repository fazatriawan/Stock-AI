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
} from "lucide-react";

const navItems = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portofolio", icon: Briefcase },
  { href: "/explorer", label: "Stock Explorer", icon: Search },
  { href: "/screener", label: "Screener", icon: Filter },
  { href: "/decisions", label: "Decision Center", icon: Target },
  { href: "/macro", label: "Macro & Policy", icon: Globe },
  { href: "/notebook", label: "Research Notebook", icon: BookOpen },
  { href: "/performance", label: "Performance Lab", icon: BarChart2 },
  { href: "/settings", label: "Data & Settings", icon: Database },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col min-h-screen sticky top-0">
      <div className="px-4 py-5 border-b border-gray-800">
        <span className="text-sm font-semibold text-gray-100 tracking-tight">Stock Intelligence</span>
        <p className="text-xs text-gray-500 mt-0.5">IDX · US</p>
      </div>
      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors",
              pathname === href
                ? "bg-gray-800 text-white font-medium"
                : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
            )}
          >
            <Icon size={15} strokeWidth={1.75} />
            {label}
          </Link>
        ))}
      </nav>
      <div className="px-4 py-3 border-t border-gray-800">
        <p className="text-xs text-gray-600">
          Data sintetis — bukan rekomendasi investasi
        </p>
      </div>
    </aside>
  );
}
