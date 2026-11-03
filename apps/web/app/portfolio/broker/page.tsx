import Link from "next/link";
import { Upload, FileText, Shield, Info } from "lucide-react";

const SUPPORTED_FORMATS = [
  {
    broker: "Semua Broker IDX",
    format: "CSV / XLSX",
    fields: "Tanggal, Ticker, Aksi (BUY/SELL), Lot/Lembar, Harga, Fee",
    notes: "Format bebas — kolom dikenali otomatis",
  },
  {
    broker: "Stockbit",
    format: "CSV Export",
    fields: "Riwayat transaksi dari menu Portofolio",
    notes: "Export manual dari aplikasi Stockbit",
  },
  {
    broker: "IPOT (Indo Premier)",
    format: "CSV Export",
    fields: "Trade history dari dashboard IPOT",
    notes: "Export manual, tidak perlu login API",
  },
  {
    broker: "Mirae Asset",
    format: "XLSX Export",
    fields: "Laporan transaksi saham",
    notes: "Export dari HOTS/NEO HOTS",
  },
];

export default function BrokerConnectionsPage() {
  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Broker Connections</h1>
        <p className="text-sm text-gray-500 mt-0.5">Sinkronisasi data portofolio melalui import file</p>
      </div>

      {/* Pendekatan */}
      <div className="rounded-xl border border-blue-800/30 bg-blue-950/15 p-4 space-y-2">
        <div className="flex items-center gap-2">
          <Shield size={14} className="text-blue-400 shrink-0" />
          <p className="text-sm font-medium text-blue-300">Pendekatan Import Manual</p>
        </div>
        <p className="text-xs text-blue-400/80 leading-relaxed">
          Stock Intelligence <strong>tidak terhubung ke broker secara langsung</strong> dan tidak pernah
          menyimpan kredensial (username/password/PIN) broker. Sinkronisasi dilakukan melalui
          file CSV atau XLSX yang Anda export secara manual dari aplikasi broker.
        </p>
        <p className="text-xs text-blue-400/60">
          Keputusan untuk memasang order sepenuhnya ada di tangan Anda — tidak ada auto-trading.
        </p>
      </div>

      {/* Import CTA */}
      <div className="bg-gray-800/40 border border-gray-700/40 rounded-xl p-5 flex items-start gap-4">
        <div className="p-2.5 bg-gray-700/50 rounded-lg">
          <Upload size={18} className="text-gray-300" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-100">Import Transaksi</p>
          <p className="text-xs text-gray-500 mt-0.5 mb-3">
            Upload file CSV atau XLSX dari broker Anda. Sistem akan mengenali kolom secara otomatis
            dan menampilkan preview sebelum data disimpan.
          </p>
          <Link
            href="/portfolio/import"
            className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white rounded-lg transition-colors"
          >
            <Upload size={12} />
            Buka Halaman Import
          </Link>
        </div>
      </div>

      {/* Format yang didukung */}
      <div className="space-y-3">
        <h2 className="text-sm font-medium text-gray-300">Format yang Didukung</h2>
        <div className="space-y-2">
          {SUPPORTED_FORMATS.map(f => (
            <div
              key={f.broker}
              className="bg-gray-800/30 border border-gray-700/40 rounded-lg px-4 py-3 flex items-start gap-3"
            >
              <FileText size={14} className="text-gray-500 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-gray-200">{f.broker}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-400 border border-gray-600/40">{f.format}</span>
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{f.fields}</p>
                <p className="text-xs text-gray-600 mt-0.5 italic">{f.notes}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Cara export */}
      <div className="space-y-3">
        <h2 className="text-sm font-medium text-gray-300">Cara Export dari Broker</h2>
        <div className="bg-gray-800/30 border border-gray-700/40 rounded-xl p-4 space-y-3 text-xs text-gray-400">
          <div className="flex items-start gap-2">
            <span className="text-gray-600 shrink-0 font-mono">1.</span>
            <p>Masuk ke aplikasi broker Anda (Stockbit, IPOT, Mirae, dll)</p>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-gray-600 shrink-0 font-mono">2.</span>
            <p>Buka menu <strong className="text-gray-300">Riwayat Transaksi</strong> atau <strong className="text-gray-300">Trade History</strong></p>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-gray-600 shrink-0 font-mono">3.</span>
            <p>Pilih rentang tanggal yang diinginkan (maks. export sesuai limit broker)</p>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-gray-600 shrink-0 font-mono">4.</span>
            <p>Klik <strong className="text-gray-300">Export</strong> / <strong className="text-gray-300">Download CSV</strong> atau <strong className="text-gray-300">Download XLSX</strong></p>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-gray-600 shrink-0 font-mono">5.</span>
            <p>Upload file tersebut di <Link href="/portfolio/import" className="text-blue-400 hover:underline">halaman Import Transaksi</Link></p>
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="flex items-start gap-2 text-xs text-gray-600">
        <Info size={12} className="shrink-0 mt-0.5 text-gray-600" />
        <p>
          Duplikat transaksi otomatis terdeteksi berdasarkan fingerprint (tanggal + ticker + aksi + harga).
          Mengimpor file yang sama dua kali aman — data tidak akan terduplikasi.
        </p>
      </div>
    </div>
  );
}
