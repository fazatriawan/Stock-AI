import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MarketStatusGrid } from "@/components/dashboard/MarketStatusGrid";
import { DataHealthStatus } from "@/components/dashboard/DataHealthStatus";

export default function OverviewPage() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Overview</h1>
          <p className="text-sm text-gray-500 mt-0.5">Ringkasan portofolio & market hari ini</p>
        </div>
        <Badge variant="warning">Data Sintetis</Badge>
      </div>

      {/* Market status */}
      <section>
        <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Status Bursa</h2>
        <MarketStatusGrid />
      </section>

      {/* Portfolio placeholder */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Total Portofolio", value: "—", sub: "Belum ada posisi" },
          { label: "Unrealized P/L", value: "—", sub: "vs harga beli rata-rata" },
          { label: "Return YTD", value: "—", sub: "vs IHSG: —" },
          { label: "Cash Tersedia", value: "—", sub: "Atur di Pengaturan" },
        ].map((stat) => (
          <Card key={stat.label}>
            <CardContent className="py-4">
              <p className="text-xs text-gray-500">{stat.label}</p>
              <p className="text-xl font-semibold text-gray-100 mt-1">{stat.value}</p>
              <p className="text-xs text-gray-600 mt-0.5">{stat.sub}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      {/* Data health */}
      <section>
        <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Status Provider Data</h2>
        <DataHealthStatus />
      </section>

      {/* Disclaimer */}
      <div className="rounded-lg border border-amber-800/40 bg-amber-950/20 px-4 py-3">
        <p className="text-xs text-amber-400/80">
          <strong>Catatan:</strong> Seluruh data yang ditampilkan saat ini adalah data sintetis untuk testing.
          Tidak ada angka yang mencerminkan kondisi pasar nyata. Sistem ini bukan nasihat investasi.
          Keputusan transaksi sepenuhnya menjadi tanggung jawab pengguna.
        </p>
      </div>
    </div>
  );
}
