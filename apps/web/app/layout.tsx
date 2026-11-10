import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { MobileNav } from "@/components/dashboard/MobileNav";
import { ChatWidget } from "@/components/chat/ChatWidget";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: "Stock Intelligence",
  description: "Personal equity research & decision support — IDX & US markets",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id" className="dark">
      <body className={`${geist.variable} ${geistMono.variable} font-sans bg-gray-950 text-gray-100 min-h-screen`}>
        {/* Mobile: topbar + drawer */}
        <MobileNav />

        <div className="flex min-h-screen">
          {/* Desktop sidebar — sembunyi di mobile */}
          <div className="hidden md:block">
            <Sidebar />
          </div>
          <main className="flex-1 overflow-auto">
            {children}
          </main>
        </div>

        {/* Chat assistant — floating, semua halaman */}
        <ChatWidget />
      </body>
    </html>
  );
}
