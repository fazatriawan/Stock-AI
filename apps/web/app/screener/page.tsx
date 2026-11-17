"use client";

import React, { useState } from "react";
import {
  api,
  type ScreenerResult,
  type ScreenerFilters,
  type MultibaggerResult,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Search, SlidersHorizontal, Sparkles, ChevronDown, ChevronUp, TrendingUp, TrendingDown, Minus, Bot, Loader2 } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

interface AiInsight {
  investment_thesis?: string;
  sector_trend?: string;
  near_term_catalysts?: string[];
  key_risks?: string[];
  research_priority?: string;
  skipped?: boolean;
  reason?: string;
}

const ACTION_VARIANT: Record<string, "success" | "danger" | "warning" | "default"> = {
  BUY: "success",
  ADD_CANDIDATE: "success",
  HOLD: "default",
  WAIT: "default",
  TRIM_CANDIDATE: "warning",
  SELL: "danger",
  INSUFFICIENT_DATA: "default",
};

const TIER_VARIANT: Record<string, "success" | "warning" | "default" | "danger"> = {
  STRONG: "success",
  MODERATE: "warning",
  WEAK: "default",
  NOT_QUALIFIED: "danger",
  INSUFFICIENT: "default",
};

const PIPELINE_LABELS: Record<string, string> = {
  QUALITY_COMPOUNDER: "Quality Compounder",
  EARNINGS_INFLECTION: "Earnings Inflection",
  TURNAROUND: "Turnaround",
  UNDERAPPRECIATED_CATALYST: "Underappreciated Catalyst",
};

// Narasi kualitatif per pipeline — menjelaskan "kenapa ini menarik" bukan hanya angka
const PIPELINE_NARRATIVE: Record<string, { title: string; why: string; signal: string }> = {
  QUALITY_COMPOUNDER: {
    title: "Quality Compounder",
    why: "ROE konsisten di atas rata-rata industri dengan FCF positif — bisnis yang mampu compounding sendiri tanpa terus-menerus butuh modal eksternal. Pasar biasanya memberi premium multiple yang persisten untuk kategori ini.",
    signal: "Cocok sebagai core holding jangka panjang. Tesis kuat selama ROE tidak terdegradasi.",
  },
  EARNINGS_INFLECTION: {
    title: "Earnings Inflection",
    why: "Terjadi akselerasi pertumbuhan laba yang baru muncul dalam 1–3 tahun terakhir. Pasar sering terlambat pricing in momentum yang baru dimulai — window of opportunity biasanya ada sebelum consensus analyst update target.",
    signal: "High conviction jika akselerasi berlanjut ke kuartal berikutnya. Watch earnings release berikutnya.",
  },
  TURNAROUND: {
    title: "Turnaround",
    why: "Valuasi tertekan sementara fundamentals (FCF, margin) mulai pulih dari titik terendah. Skenario asymmetric: downside terbatas karena sudah diharga buruk, upside besar jika recovery berlanjut.",
    signal: "High risk, high reward. Konfirmasi butuh 2–3 kuartal berturutan sebelum ukuran posisi diperbesar.",
  },
  UNDERAPPRECIATED_CATALYST: {
    title: "Underappreciated Catalyst",
    why: "Diskon ≥20% terhadap peer dengan profitabilitas yang sebenarnya kuat — ada mismatch antara persepsi pasar dan realita bisnis. Biasanya karena liquidity rendah, coverage analyst minim, atau nama saham kurang populer.",
    signal: "Catalyst biasanya datang dari rerating oleh analis baru atau aksi korporasi (rights issue, buyback, rights offering).",
  },
};

// Tema struktural per sektor — berlabel jelas sebagai opini riset jangka menengah
const SECTOR_STRUCTURAL_THEME: Record<string, { trend: string; catalyst: string; risk: string }> = {
  Finance: {
    trend: "Suku bunga BI tinggi menguntungkan NIM perbankan. Digitalisasi layanan keuangan (open banking, super-app) membuka revenue stream baru di luar kredit.",
    catalyst: "Penurunan suku bunga BI (bila terjadi) akan re-rating PBV. Ekspansi ke segmen MSME dan fintech lending.",
    risk: "Tekanan NPL jika siklus kredit memburuk. Kompetisi fintech menekan fee income.",
  },
  Telecoms: {
    trend: "5G rollout IDX masih tahap awal — penetrasi rendah berarti runway panjang. Konsolidasi industri (3 operator besar) mengurangi price war yang selama ini menekan ARPU.",
    catalyst: "Monetisasi infrastruktur pasif (menara, fiber) via spin-off. IoT enterprise sebagai engine pertumbuhan baru.",
    risk: "Capex 5G besar menekan free cash flow jangka pendek.",
  },
  Technology: {
    trend: "AI adoption enterprise dan digitalisasi UMKM mendorong demand platform SaaS lokal. Valuasi sektor ini di IDX masih compressed vs peer Asia Tenggara.",
    catalyst: "Partnership dengan hyperscaler (AWS, Azure, GCP). Pemerintah mendorong pengadaan produk lokal (P3DN).",
    risk: "Talent war membuat biaya SDM naik. Kompetisi dari produk global yang masuk via cloud.",
  },
  Energy: {
    trend: "Hilirisasi batubara dan gas (DMO, gasifikasi) memberikan margin premium bagi produsen domestik. Transisi ke EV membuka pasar komponen baterai.",
    catalyst: "Harga komoditas global naik (driven geopolitik). Ekspor ke pasar Asia Timur yang masih bergantung fosil.",
    risk: "Tekanan ESG dari investor global. Regulasi transisi energi bisa memotong life-of-asset.",
  },
  Healthcare: {
    trend: "Populasi aging Indonesia + ekspansi JKN memperluas addressable market. Under-penetrated vs Malaysia dan Thailand — ruang tumbuh organik masih besar.",
    catalyst: "Kebijakan mandatory health insurance coverage yang semakin luas. Medical tourism domestik post-COVID.",
    risk: "Ketergantungan bahan baku impor (API farmasi). Tarif BPJS yang sering ditekan.",
  },
  Consumer: {
    trend: "Recovery daya beli middle class setelah tekanan inflasi 2022–2024. Urbanisasi dan pergeseran ke konsumsi branded masih berlanjut jangka panjang.",
    catalyst: "Penurunan harga pangan (El Niño reda) memperbesar disposable income. Bonus demografi 2030.",
    risk: "El Niño atau gangguan rantai pasok pangan bisa tekan margin. Kompetisi private label dari modern retail.",
  },
  Property: {
    trend: "Backlog rumah affordable masih besar. Program 3 juta rumah pemerintah menjadi demand driver jangka menengah bagi developer mid-low.",
    catalyst: "Penurunan suku bunga KPR. Pembangunan IKN membuka demand properti komersial di Kalimantan Timur.",
    risk: "Tingkat suku bunga tinggi menekan affordability dan volume penjualan saat ini.",
  },
  Materials: {
    trend: "Hilirisasi nikel dan bauksit — smelter domestik mendapat premium atas raw ore. Kebijakan biodiesel B40/B50 mempertahankan floor demand CPO.",
    catalyst: "Demand baterai EV global naik — nikel dan litium menjadi critical mineral.",
    risk: "Harga komoditas volatile bergantung demand China. Risiko over-supply smelter nikel.",
  },
  Industrial: {
    trend: "Belanja infrastruktur PSN (Proyek Strategis Nasional) + IKN memberikan order visibility 3–5 tahun ke depan bagi kontraktor dan material building.",
    catalyst: "Diversifikasi supply chain dari China mendorong FDI ke kawasan industri IDX.",
    risk: "Keterlambatan pembayaran proyek pemerintah menekan cashflow. Risiko proyek mangkrak jika anggaran dipangkas.",
  },
};

const SECTORS = [
  "Finance",
  "Financials",
  "Consumer",
  "Telecoms",
  "Energy",
  "Materials",
  "Healthcare",
  "Industrial",
  "Technology",
  "Property",
];
const EXCHANGES = ["IDX", "NASDAQ", "NYSE"];

interface SectorDefault {
  roe: string;
  peMin: string;
  peMax: string;
  score: string;
  rationale: string;
  roeReason: string;
  peReason: string;
  scoreReason: string;
}

const SECTOR_DEFAULTS: Record<string, SectorDefault> = {
  "": {
    roe: "8", peMin: "3", peMax: "25", score: "50",
    rationale: "Standar universal untuk semua sektor — titik tengah yang tidak memotong saham sehat dari sektor apapun, sambil tetap menyaring perusahaan berkualitas rendah.",
    roeReason: "8% adalah ROE minimum lintas-sektor: cukup tinggi untuk menyaring perusahaan tidak efisien, cukup rendah untuk tidak membuang sektor property/infrastruktur yang ROE-nya struktural lebih rendah.",
    peReason: "P/E min 3 memfilter perusahaan rugi atau earnings cyclical puncak yang membuat P/E semu rendah. P/E maks 25 cukup longgar untuk healthcare/tech growth, tapi masih membuang saham yang overvalued tanpa alasan.",
    scoreReason: "Skor 50 dari 100 berarti 'di atas rata-rata kelengkapan & kualitas data'. Di bawah ini, data terlalu tipis untuk membuat keputusan yang bermakna.",
  },
  Finance: {
    roe: "12", peMin: "5", peMax: "18", score: "50",
    rationale: "Perbankan & keuangan punya struktur bisnis unik: ROE didorong leverage, bukan efisiensi aset murni. Valuasi berbeda — P/E rendah justru bisa mengindikasikan kualitas.",
    roeReason: "Bank yang sehat di IDX biasanya ROE 15–20%. Menetapkan minimum 12% menyaring bank yang gagal menghasilkan return memadai di atas cost of equity. Di bawah 12% biasanya ada masalah NPL atau capital adequacy.",
    peReason: "Sektor keuangan secara historis trade di P/E 8–15x di IDX. P/E di atas 18 untuk bank lokal biasanya berarti premium berlebih atau momentum driven. P/E min 5 membuang perusahaan keuangan dengan earnings tidak stabil.",
    scoreReason: "Data keuangan bank umumnya lebih lengkap dan terstandarisasi (OJK reporting), sehingga ambang skor 50 cukup untuk seleksi awal.",
  },
  Financials: {
    roe: "12", peMin: "5", peMax: "18", score: "50",
    rationale: "Sama dengan Finance — mencakup perusahaan asuransi, sekuritas, multifinance yang struktur labanya mirip perbankan.",
    roeReason: "12% adalah ROE minimum untuk memastikan perusahaan keuangan non-bank menghasilkan return di atas rata-rata cost of capital Indonesia (~10%).",
    peReason: "Multifinance dan asuransi trade lebih rendah dari bank, namun tetap terbatas di bawah 18x untuk menghindari spekulasi.",
    scoreReason: "Perusahaan keuangan umumnya memiliki data terstruktur dari laporan OJK, skor 50 sudah representatif.",
  },
  Consumer: {
    roe: "10", peMin: "5", peMax: "25", score: "50",
    rationale: "Consumer staples & discretionary punya pricing power — brand moat yang kuat membuat P/E premium wajar. Namun ROE harus tetap memadai karena bisnis ini tidak butuh capex besar.",
    roeReason: "Consumer companies idealnya ROE > 10% karena tidak butuh modal besar untuk tumbuh. ROE di bawah 10% mengindikasikan margin yang tertekan atau manajemen yang tidak efisien dalam mengalokasikan modal.",
    peReason: "Brand consumer bisa wajar di P/E 20–25x karena stabilitas earnings. Namun di atas 25x di IDX biasanya sudah pricing pertumbuhan yang terlalu optimistis. P/E min 5 membuang consumer company dengan earnings tidak konsisten.",
    scoreReason: "Consumer sector umumnya data lengkap; skor 50 memastikan kita hanya melihat perusahaan dengan history yang cukup untuk dinilai.",
  },
  Telecoms: {
    roe: "8", peMin: "5", peMax: "20", score: "50",
    rationale: "Telekomunikasi adalah mature sector dengan capex infrastruktur besar. ROE moderate wajar karena asset-heavy. Pertumbuhan lebih stabil, sehingga valuasi tidak perlu tinggi.",
    roeReason: "Operator telco harus maintain jaringan yang mahal — ROE 8% sudah mencerminkan bisnis yang wajar. Yang di bawah 8% biasanya sedang fase heavy investment atau kehilangan pangsa pasar.",
    peReason: "Telco trade di P/E 10–18x secara global. Maks 20 memberi ruang untuk premium digitalisasi. P/E min 5 membuang operator yang earnings-nya sangat tertekan oleh price war.",
    scoreReason: "3 operator besar IDX (TLKM, EXCL, ISAT) umumnya data lengkap. Skor 50 relevan untuk menyaring emiten telco kecil dengan data tipis.",
  },
  Energy: {
    roe: "8", peMin: "3", peMax: "15", score: "45",
    rationale: "Energi adalah sektor siklikal — P/E bisa meledak di puncak siklus komoditas. Valuasi yang 'mahal' di P/E sering kali justru tanda earnings sudah di puncak. Gunakan standar yang lebih konservatif.",
    roeReason: "Di puncak siklus batubara/minyak, ROE bisa mencapai 30–50% — sementara di lembah siklus bisa 2–5%. ROE min 8% memfilter perusahaan energi yang bahkan di kondisi komoditas baik pun tidak efisien.",
    peReason: "Energy P/E di bawah 10 saat komoditas tinggi = warning sinyal bahwa pasar ekspektasi earnings akan turun. P/E maks 15 menghindari membeli di puncak siklus. P/E min 3 membuang yang sudah di ambang rugi.",
    scoreReason: "Sektor energi kecil di IDX sering data tidak lengkap; skor 45 lebih realistis untuk mendapatkan kandidat yang layak diriset.",
  },
  Materials: {
    roe: "8", peMin: "3", peMax: "15", score: "45",
    rationale: "Sama seperti energi, bahan baku sangat siklikal terhadap harga komoditas global (nikel, CPO, batu bara). Standar konservatif untuk menghindari jebakan peak-cycle valuation.",
    roeReason: "Produsen bahan baku yang tidak mampu ROE 8% bahkan saat harga komoditas tinggi kemungkinan memiliki cost structure yang tidak kompetitif atau sudah di tahap deplesi aset.",
    peReason: "Materials P/E maks 15 adalah 'rule of thumb' klasik untuk menghindari membeli komoditas saat earnings peak. Kombinasi P/E rendah + ROE tinggi = tanda danger zone, bukan value.",
    scoreReason: "Banyak emiten materials di IDX adalah perusahaan kecil dengan pelaporan tidak konsisten; skor 45 memberi lebih banyak kandidat tanpa mengorbankan terlalu banyak kualitas.",
  },
  Healthcare: {
    roe: "10", peMin: "8", peMax: "35", score: "50",
    rationale: "Healthcare adalah growth sector yang undervalued di IDX. P/E premium wajar karena visibilitas pertumbuhan tinggi (JKN, aging population). P/E min lebih tinggi untuk membuang rumah sakit atau farmasi yang earnings-nya tidak stabil.",
    roeReason: "Perusahaan healthcare dengan ROE di bawah 10% biasanya sangat capex-heavy tanpa pricing power — tidak ideal sebagai investasi jangka menengah. ROE 10%+ menandakan manajemen yang bisa monetize aset medis dengan efisien.",
    peReason: "P/E min 8 membuang healthcare companies dengan earnings sangat volatile atau one-off. P/E maks 35 memberi ruang untuk growth premium yang wajar di sektor ini — MIKA, HEAL, KLBF secara historis trade 20–35x di fase pertumbuhan.",
    scoreReason: "Healthcare berkembang pesat tapi banyak emiten baru di IDX dengan data terbatas; skor 50 memastikan hanya perusahaan dengan track record yang masuk.",
  },
  Industrial: {
    roe: "8", peMin: "5", peMax: "20", score: "45",
    rationale: "Sektor industri di IDX mencakup kontraktor, manufaktur berat, kawasan industri — semua capex-heavy. ROE moderate wajar, pertumbuhan lebih terikat siklus belanja pemerintah.",
    roeReason: "Kontraktor dan manufaktur yang tidak mencapai ROE 8% biasanya terlalu tergantung utang atau inefficient dalam eksekusi proyek. 8% juga berarti margin EBIT cukup untuk menutup cost of debt rata-rata 7–9% di Indonesia.",
    peReason: "Industrial tidak tumbuh secepat consumer atau healthcare. P/E maks 20 sudah premium untuk sektor ini. P/E min 5 membuang kontraktor yang earnings-nya semu (proyek satu kali) atau tergantung utang baru.",
    scoreReason: "Banyak emiten industrial kecil dengan pelaporan tidak teratur. Skor 45 memberikan lebih banyak kandidat untuk riset sambil tetap membuang yang data-nya sangat tipis.",
  },
  Technology: {
    roe: "8", peMin: "8", peMax: "40", score: "50",
    rationale: "Teknologi di IDX masih tahap awal — valuasi tinggi bisa wajar jika ada revenue growth yang kuat. P/E maks paling longgar di antara semua sektor, tapi ROE dan skor harus tetap terjaga.",
    roeReason: "Tech companies yang ROE-nya di bawah 8% biasanya masih burning cash atau model bisnisnya belum prove out. Di IDX, tech berkualitas (MTDL, BUKA yang mulai profitable) sudah bisa ROE > 8%.",
    peReason: "P/E maks 40 adalah batas atas yang wajar untuk tech di IDX — above that, hanya cocok untuk speculative buying bukan value investing. P/E min 8 membuang perusahaan tech yang earnings-nya sangat tidak stabil atau baru satu kuartal profit.",
    scoreReason: "Perusahaan teknologi di IDX bervariasi — dari yang data lengkap (MTDL, MLPT) hingga startup yang baru listing. Skor 50 memastikan kita hanya melihat yang sudah ada track record.",
  },
  Property: {
    roe: "5", peMin: "5", peMax: "20", score: "45",
    rationale: "Properti adalah sektor dengan ROE struktural paling rendah karena aset-nya dinilai pada harga perolehan (bukan market value). Jangan pakai standar ROE yang sama dengan sektor lain.",
    roeReason: "Developer properti di IDX yang ROE-nya di atas 5% sudah termasuk efisien — aset tanah dan bangunan dinilai di buku, bukan market value. Menetapkan ROE min 10% akan membuang hampir semua developer yang sehat.",
    peReason: "Properti secara global trade di P/E rendah karena earnings cyclical dan sering mengandung unrealized gains. P/E maks 20 sudah cukup generous. P/E min 5 membuang developer yang earnings-nya hampir nol atau sangat tergantung penjualan bulk.",
    scoreReason: "Banyak developer properti IDX dengan data tidak lengkap karena pendapatan tidak diakui sampai serah terima unit. Skor 45 lebih realistis.",
  },
};

function FreshnessChip({ freshness }: { freshness: string }) {
  const color =
    freshness === "FRESH"
      ? "text-emerald-400"
      : freshness === "ACCEPTABLE"
        ? "text-amber-400"
        : "text-slate-300";
  return <span className={`text-xs ${color}`}>{freshness}</span>;
}

function ScorePill({ score }: { score: number }) {
  const bg =
    score >= 60
      ? "bg-emerald-900/30 text-emerald-300"
      : score >= 45
        ? "bg-amber-900/30 text-amber-300"
        : "bg-gray-800 text-gray-400";
  return <span className={`text-xs px-1.5 py-0.5 rounded ${bg}`}>{score.toFixed(0)}</span>;
}

export default function ScreenerPage() {
  const [activeTab, setActiveTab] = useState<"standard" | "multibagger">("standard");

  // Standard Screener state
  const [results, setResults] = useState<ScreenerResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [stdAiInsights, setStdAiInsights] = useState<Record<string, AiInsight>>({});
  const [stdAiLoading, setStdAiLoading] = useState<Record<string, boolean>>({});
  const [stdExpanded, setStdExpanded] = useState<string | null>(null);
  const [showStandards, setShowStandards] = useState(false);

  // Filter state
  const [sector, setSector] = useState("");
  const [exchange, setExchange] = useState("");
  const [minRoe, setMinRoe] = useState("");
  const [maxPe, setMaxPe] = useState("");
  const [minPe, setMinPe] = useState("");
  const [minScore, setMinScore] = useState("");
  const [action, setAction] = useState("");

  // Multibagger Lab state
  const [mbResults, setMbResults] = useState<MultibaggerResult[]>([]);
  const [mbLoading, setMbLoading] = useState(false);
  const [mbError, setMbError] = useState<string | null>(null);
  const [mbSearched, setMbSearched] = useState(false);
  const [mbMinTier, setMbMinTier] = useState("MODERATE");
  const [mbPipelineFilter, setMbPipelineFilter] = useState("");
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [sectorRotation, setSectorRotation] = useState<Record<string, { signal: string; return_1m: number | null; momentum_score: number | null }>>({});
  const [aiInsights, setAiInsights] = useState<Record<string, AiInsight>>({});
  const [aiLoading, setAiLoading] = useState<Record<string, boolean>>({});

  async function fetchAiInsight(item: MultibaggerResult, rot?: { signal: string; return_1m: number | null }) {
    const key = item.canonical_symbol;
    if (aiInsights[key] || aiLoading[key]) return;
    setAiLoading(prev => ({ ...prev, [key]: true }));
    try {
      const res = await fetch(`${API_BASE}/screener/insight`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: item.canonical_symbol,
          sector: item.sector,
          pipelines: item.score.pipelines_matched ?? [],
          tier: item.score.tier,
          total_score: item.score.total_score,
          strengths: item.score.strengths ?? [],
          concerns: item.score.concerns ?? [],
          pe_ratio: item.pe_ratio,
          roe: item.roe,
          net_margin: item.net_margin,
          revenue_growth_1y: item.revenue_growth_1y,
          debt_to_equity: item.debt_to_equity,
          sector_signal: rot?.signal ?? null,
          sector_return_1m: rot?.return_1m ?? null,
        }),
      });
      const data: AiInsight = await res.json();
      setAiInsights(prev => ({ ...prev, [key]: data }));
    } catch {
      setAiInsights(prev => ({ ...prev, [key]: { skipped: true, reason: "Gagal menghubungi AI" } }));
    } finally {
      setAiLoading(prev => ({ ...prev, [key]: false }));
    }
  }

  async function fetchStdInsight(r: ScreenerResult) {
    const key = r.canonical_symbol;
    if (stdAiInsights[key] || stdAiLoading[key]) {
      setStdExpanded(prev => prev === key ? null : key);
      return;
    }
    setStdExpanded(key);
    setStdAiLoading(prev => ({ ...prev, [key]: true }));
    try {
      const res = await fetch(`${API_BASE}/screener/insight`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: r.canonical_symbol,
          sector: r.sector,
          pipelines: [],
          tier: r.composite_score >= 70 ? "STRONG" : r.composite_score >= 50 ? "MODERATE" : "WEAK",
          total_score: r.composite_score,
          strengths: [],
          concerns: [],
          pe_ratio: r.pe_ratio,
          roe: r.roe ? r.roe * 100 : null,
        }),
      });
      const data: AiInsight = await res.json();
      setStdAiInsights(prev => ({ ...prev, [key]: data }));
    } catch {
      setStdAiInsights(prev => ({ ...prev, [key]: { skipped: true, reason: "Gagal menghubungi AI" } }));
    } finally {
      setStdAiLoading(prev => ({ ...prev, [key]: false }));
    }
  }

  function applySectorDefaults(s: string) {
    const d = SECTOR_DEFAULTS[s] ?? SECTOR_DEFAULTS[""];
    setMinRoe(d.roe);
    setMinPe(d.peMin);
    setMaxPe(d.peMax);
    setMinScore(d.score);
  }

  async function runScreen() {
    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const filters: ScreenerFilters = { limit: 100 };
      if (sector) filters.sector = sector;
      if (exchange) filters.exchange = exchange;
      if (minRoe) filters.min_roe = parseFloat(minRoe) / 100;
      if (maxPe) filters.max_pe = parseFloat(maxPe);
      if (minPe) filters.min_pe = parseFloat(minPe);
      if (minScore) filters.min_composite = parseFloat(minScore);
      if (action) filters.action = action;
      const res = await api.screener.screen(filters);
      setResults(res.results);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Screener gagal");
    } finally {
      setLoading(false);
    }
  }

  async function runMultibaggerScreen() {
    setMbLoading(true);
    setMbError(null);
    setMbSearched(true);
    try {
      const [mbRes, rotationRes] = await Promise.allSettled([
        api.screener.multibagger({
          sector: sector || undefined,
          exchange: exchange || undefined,
          min_tier: mbMinTier,
          limit: 100,
        }),
        fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "/api/v1"}/screener/sectors/rotation?exchange=${exchange || "IDX"}`).then(r => r.json()),
      ]);
      if (mbRes.status === "fulfilled") setMbResults(mbRes.value.results);
      else throw new Error((mbRes.reason as Error).message);
      if (rotationRes.status === "fulfilled") {
        const byKey: Record<string, { signal: string; return_1m: number | null; momentum_score: number | null }> = {};
        for (const s of (rotationRes.value?.all_sectors ?? [])) {
          byKey[s.sector] = { signal: s.signal, return_1m: s.return_1m, momentum_score: s.momentum_score };
        }
        setSectorRotation(byKey);
      }
    } catch (e) {
      setMbError(e instanceof Error ? e.message : "Multibagger screener gagal");
    } finally {
      setMbLoading(false);
    }
  }

  function reset() {
    setSector("");
    setExchange("");
    setMinRoe("");
    setMaxPe("");
    setMinPe("");
    setMinScore("");
    setAction("");
    setResults([]);
    setHasSearched(false);
    setMbResults([]);
    setMbSearched(false);
    setMbPipelineFilter("");
    setSectorRotation({});
  }

  const filteredMbResults = mbPipelineFilter
    ? mbResults.filter(r => r.score.pipelines_matched?.includes(mbPipelineFilter))
    : mbResults;

  return (
    <div className="p-6 space-y-5">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Screener & Multibagger Lab</h1>
          <p className="text-xs text-slate-300 mt-0.5">
            Saring kandidat riset saham berdasarkan fundamental, teknikal, & 4 pipeline Multibagger (PRD v1.7.1)
          </p>
        </div>

        {/* Tab switcher */}
        <div className="inline-flex rounded-lg bg-gray-800/70 p-1 border border-gray-700/60 self-start">
          <button
            onClick={() => setActiveTab("standard")}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === "standard"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Screener Umum
          </button>
          <button
            onClick={() => setActiveTab("multibagger")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              activeTab === "multibagger"
                ? "bg-emerald-600 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            <Sparkles size={12} />
            Multibagger Lab (4 Pipeline)
          </button>
        </div>
      </div>

      {activeTab === "standard" ? (
        <>
          {/* Filter panel */}
          <div className="bg-gray-800/40 border border-gray-700/50 rounded-xl p-4 space-y-4">
            <div className="flex items-center gap-2 text-xs text-gray-400 font-medium">
              <SlidersHorizontal size={13} /> Filter Fundamental & Teknikal
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-slate-300 mb-1">Sektor</label>
                <select
                  value={sector}
                  onChange={e => { setSector(e.target.value); applySectorDefaults(e.target.value); }}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                >
                  <option value="">Semua</option>
                  {SECTORS.map(s => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">Bursa</label>
                <select
                  value={exchange}
                  onChange={e => setExchange(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                >
                  <option value="">Semua</option>
                  {EXCHANGES.map(x => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">ROE min (%)</label>
                <input
                  type="number"
                  value={minRoe}
                  onChange={e => setMinRoe(e.target.value)}
                  placeholder="cth: 10"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">P/E maks</label>
                <input
                  type="number"
                  value={maxPe}
                  onChange={e => setMaxPe(e.target.value)}
                  placeholder="cth: 20"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">P/E min</label>
                <input
                  type="number"
                  value={minPe}
                  onChange={e => setMinPe(e.target.value)}
                  placeholder="cth: 3"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">Skor komposit min</label>
                <input
                  type="number"
                  value={minScore}
                  onChange={e => setMinScore(e.target.value)}
                  placeholder="cth: 50"
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">Sinyal engine</label>
                <select
                  value={action}
                  onChange={e => setAction(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-gray-500"
                >
                  <option value="">Semua</option>
                  {["BUY", "WAIT", "HOLD", "TRIM_CANDIDATE", "SELL"].map(a => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex gap-2 pt-1 flex-wrap items-center">
              <button
                onClick={runScreen}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
              >
                <Search size={12} />
                {loading ? "Memuat..." : "Jalankan Screener"}
              </button>
              <button
                onClick={reset}
                className="px-3 py-1.5 text-xs text-slate-300 hover:text-gray-300 transition-colors"
              >
                Reset
              </button>
              <button
                onClick={() => setShowStandards(v => !v)}
                className="ml-auto flex items-center gap-1 px-2.5 py-1.5 text-xs text-blue-400 hover:text-blue-300 border border-blue-900/50 hover:border-blue-700/50 rounded-lg transition-colors"
              >
                {showStandards ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                {showStandards ? "Sembunyikan" : "Lihat dasar penetapan standar"}
              </button>
            </div>

            {/* Panel penjelasan standar */}
            {showStandards && (() => {
              const key = sector || "";
              const d = SECTOR_DEFAULTS[key] ?? SECTOR_DEFAULTS[""];
              const label = key
                ? key
                : "Semua Sektor";
              return (
                <div className="mt-3 rounded-lg border border-blue-900/40 bg-blue-950/20 p-4 space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-xs font-semibold text-blue-300">Dasar Penetapan Standar — {label}</p>
                      <p className="text-[11px] text-gray-400 mt-0.5 leading-relaxed">{d.rationale}</p>
                    </div>
                    <span className="shrink-0 text-[10px] px-2 py-0.5 rounded-full bg-blue-900/40 text-blue-400 border border-blue-800/40">
                      {d.roe}% ROE · P/E {d.peMin}–{d.peMax} · Skor ≥{d.score}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <p className="text-[11px] font-semibold text-emerald-400 mb-1">ROE min {d.roe}%</p>
                      <p className="text-[11px] text-gray-300 leading-relaxed">{d.roeReason}</p>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <p className="text-[11px] font-semibold text-amber-400 mb-1">P/E {d.peMin}–{d.peMax}</p>
                      <p className="text-[11px] text-gray-300 leading-relaxed">{d.peReason}</p>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <p className="text-[11px] font-semibold text-purple-400 mb-1">Skor komposit ≥{d.score}</p>
                      <p className="text-[11px] text-gray-300 leading-relaxed">{d.scoreReason}</p>
                    </div>
                  </div>
                  <p className="text-[10px] text-slate-400 italic">
                    * Standar ini di-auto-isi saat memilih sektor. Anda tetap bisa mengubah nilai secara manual sebelum menjalankan screener.
                  </p>
                </div>
              );
            })()}
          </div>

          {error && (
            <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {/* Results table */}
          {results.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-slate-300">{results.length} saham ditemukan</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-300 border-b border-gray-800">
                      <th className="text-left py-2 pr-3">Ticker</th>
                      <th className="text-left py-2 pr-3">Sektor</th>
                      <th className="text-right py-2 pr-3">Harga</th>
                      <th className="text-right py-2 pr-3">PE</th>
                      <th className="text-right py-2 pr-3">ROE%</th>
                      <th className="text-right py-2 pr-3">RSI</th>
                      <th className="text-center py-2 pr-3">SMA200</th>
                      <th className="text-right py-2 pr-3">Skor</th>
                      <th className="text-center py-2 pr-3">Sinyal</th>
                      <th className="text-center py-2 pr-3">Data</th>
                      <th className="text-center py-2">AI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map(r => {
                      const ticker = r.canonical_symbol.split(":")[1] ?? r.canonical_symbol;
                      const key = r.canonical_symbol;
                      const insight = stdAiInsights[key];
                      const isExpanded = stdExpanded === key;
                      return (
                        <React.Fragment key={r.instrument_id}>
                        <tr className="border-b border-gray-800/50 hover:bg-gray-800/30">
                          <td className="py-2 pr-3">
                            <span className="font-medium text-gray-100">{ticker}</span>
                            {r.company_name && (
                              <p className="text-slate-300 truncate max-w-[120px]">
                                {r.company_name}
                              </p>
                            )}
                          </td>
                          <td className="py-2 pr-3 text-gray-400">{r.sector ?? "—"}</td>
                          <td className="py-2 pr-3 text-right text-gray-300">
                            {r.current_price != null
                              ? `Rp ${r.current_price.toLocaleString("id-ID")}`
                              : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right text-gray-300">
                            {r.pe_ratio != null ? r.pe_ratio.toFixed(1) : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right text-gray-300">
                            {r.roe != null ? (r.roe * 100).toFixed(1) : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right text-gray-300">
                            {r.rsi_14 != null ? r.rsi_14.toFixed(0) : "—"}
                          </td>
                          <td className="py-2 pr-3 text-center">
                            {r.above_sma_200 == null ? (
                              "—"
                            ) : r.above_sma_200 ? (
                              <span className="text-emerald-400">↑</span>
                            ) : (
                              <span className="text-red-400">↓</span>
                            )}
                          </td>
                          <td className="py-2 pr-3 text-right">
                            <ScorePill score={r.composite_score} />
                          </td>
                          <td className="py-2 pr-3 text-center">
                            <Badge variant={ACTION_VARIANT[r.action]}>{r.action}</Badge>
                          </td>
                          <td className="py-2 pr-3 text-center">
                            <FreshnessChip freshness={r.data_freshness} />
                          </td>
                          <td className="py-2 text-center">
                            <button
                              onClick={() => fetchStdInsight(r)}
                              title="Analisis AI"
                              className={`p-1 rounded transition-colors ${
                                isExpanded
                                  ? "text-purple-400 bg-purple-900/30"
                                  : "text-gray-500 hover:text-purple-400 hover:bg-purple-900/20"
                              }`}
                            >
                              {stdAiLoading[key] ? (
                                <Loader2 size={12} className="animate-spin" />
                              ) : (
                                <Bot size={12} />
                              )}
                            </button>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="border-b border-gray-800/50 bg-gray-900/40">
                            <td colSpan={11} className="px-4 py-3">
                              {stdAiLoading[key] ? (
                                <div className="flex items-center gap-2 text-xs text-purple-400">
                                  <Loader2 size={12} className="animate-spin" /> Meminta analisis AI…
                                </div>
                              ) : insight?.skipped ? (
                                <p className="text-xs text-red-400">{insight.reason ?? "AI tidak tersedia"}</p>
                              ) : insight ? (
                                <div className="space-y-2.5">
                                  <div className="flex items-center gap-1.5 text-xs font-medium text-purple-300">
                                    <Bot size={12} /> Analisis AI — {ticker}
                                  </div>
                                  {insight.investment_thesis && (
                                    <div>
                                      <p className="text-[11px] font-semibold text-gray-400 mb-0.5">Tesis Investasi</p>
                                      <p className="text-xs text-gray-200 leading-relaxed">{insight.investment_thesis}</p>
                                    </div>
                                  )}
                                  {insight.sector_trend && (
                                    <div>
                                      <p className="text-[11px] font-semibold text-gray-400 mb-0.5">Tren Sektor</p>
                                      <p className="text-xs text-gray-300 leading-relaxed">{insight.sector_trend}</p>
                                    </div>
                                  )}
                                  <div className="grid grid-cols-2 gap-3">
                                    {insight.near_term_catalysts && insight.near_term_catalysts.length > 0 && (
                                      <div>
                                        <p className="text-[11px] font-semibold text-emerald-400 mb-1">Katalis Dekat</p>
                                        <ul className="space-y-0.5">
                                          {insight.near_term_catalysts.map((c, i) => (
                                            <li key={i} className="text-xs text-gray-300 flex gap-1.5">
                                              <span className="text-emerald-500 mt-0.5">▸</span>{c}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                    {insight.key_risks && insight.key_risks.length > 0 && (
                                      <div>
                                        <p className="text-[11px] font-semibold text-red-400 mb-1">Risiko Utama</p>
                                        <ul className="space-y-0.5">
                                          {insight.key_risks.map((r, i) => (
                                            <li key={i} className="text-xs text-gray-300 flex gap-1.5">
                                              <span className="text-red-500 mt-0.5">▸</span>{r}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                  </div>
                                  {insight.research_priority && (
                                    <p className="text-[11px] text-purple-400 italic">{insight.research_priority}</p>
                                  )}
                                </div>
                              ) : null}
                            </td>
                          </tr>
                        )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {hasSearched && !loading && results.length === 0 && !error && (
            <div className="text-center py-12 text-slate-300 space-y-2">
              <Search size={28} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">Tidak ada saham yang cocok dengan filter ini</p>
              <p className="text-xs text-slate-300 max-w-sm mx-auto">
                Screener memerlukan data fundamental lengkap (revenue growth, EPS, ROE, dll). Jika
                hasil selalu 0, jalankan{" "}
                <strong className="text-slate-300">refresh fundamentals</strong> di halaman{" "}
                <a href="/settings" className="text-blue-500 hover:underline">
                  Settings
                </a>{" "}
                terlebih dahulu.
              </p>
            </div>
          )}

          {!hasSearched && (
            <div className="text-center py-16 text-slate-300">
              <SlidersHorizontal size={28} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">Atur filter di atas, lalu klik Jalankan Screener</p>
            </div>
          )}
        </>
      ) : (
        /* Multibagger Research Lab Tab */
        <div className="space-y-4">
          <div className="bg-gray-800/40 border border-emerald-800/30 rounded-xl p-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs text-emerald-400 font-medium">
                <Sparkles size={13} /> MULTI-01 & MULTI-02 — 4 Pipeline Riset & Reverse Scenario
              </div>
              <span className="text-[11px] text-slate-300">
                Output adalah kandidat riset, bukan sinyal beli otomatis
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs text-slate-300 mb-1">Bursa</label>
                <select
                  value={exchange}
                  onChange={e => setExchange(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                >
                  <option value="">Semua</option>
                  {EXCHANGES.map(x => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">Sektor</label>
                <select
                  value={sector}
                  onChange={e => setSector(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                >
                  <option value="">Semua</option>
                  {SECTORS.map(s => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">Tier Minimum</label>
                <select
                  value={mbMinTier}
                  onChange={e => setMbMinTier(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                >
                  <option value="STRONG">STRONG (≥70)</option>
                  <option value="MODERATE">MODERATE (≥50)</option>
                  <option value="WEAK">WEAK (≥30)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-300 mb-1">Filter Pipeline (MULTI-01)</label>
                <select
                  value={mbPipelineFilter}
                  onChange={e => setMbPipelineFilter(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200"
                >
                  <option value="">Semua Pipeline</option>
                  {Object.entries(PIPELINE_LABELS).map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex gap-2 pt-1">
              <button
                onClick={runMultibaggerScreen}
                disabled={mbLoading}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs rounded-lg transition-colors disabled:opacity-50"
              >
                <Sparkles size={12} />
                {mbLoading ? "Memindai Kandidat..." : "Cari Kandidat Multibagger"}
              </button>
              <button
                onClick={reset}
                className="px-3 py-1.5 text-xs text-slate-300 hover:text-gray-300 transition-colors"
              >
                Reset
              </button>
            </div>
          </div>

          {mbError && (
            <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-400">
              {mbError}
            </div>
          )}

          {filteredMbResults.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs text-slate-300">
                {filteredMbResults.length} kandidat riset ditemukan
              </p>

              {filteredMbResults.map(item => {
                const isExpanded = expandedSymbol === item.canonical_symbol;
                const pipelines = item.score.pipelines_matched ?? [];
                const scenarios = item.score.reverse_scenarios ?? [];

                return (
                  <div
                    key={item.instrument_id}
                    className="bg-gray-800/30 border border-gray-700/50 rounded-xl p-4 space-y-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-gray-100">
                            {item.canonical_symbol}
                          </span>
                          <Badge variant={TIER_VARIANT[item.score.tier] ?? "default"}>
                            {item.score.tier} ({item.score.total_score.toFixed(0)}/100)
                          </Badge>
                          <span className="text-xs text-slate-300">{item.sector ?? "—"}</span>
                        </div>
                        {item.company_name && (
                          <p className="text-xs text-gray-400 mt-0.5">{item.company_name}</p>
                        )}
                      </div>

                      <div className="text-right text-xs">
                        <p className="text-gray-200 font-medium">
                          {item.current_price != null
                            ? `Rp ${item.current_price.toLocaleString("id-ID")}`
                            : "Harga N/A"}
                        </p>
                        <p className="text-slate-300">
                          PE: {item.pe_ratio != null ? `${item.pe_ratio.toFixed(1)}x` : "—"} · ROE:{" "}
                          {item.roe != null ? `${item.roe.toFixed(1)}%` : "—"} · Data:{" "}
                          {(item.score.data_completeness * 100).toFixed(0)}%
                        </p>
                      </div>
                    </div>

                    {/* Matched Pipelines + narasi kualitatif */}
                    {pipelines.length > 0 ? (
                      <div className="space-y-2">
                        {pipelines.map(p => {
                          const narrative = PIPELINE_NARRATIVE[p];
                          return (
                            <div key={p} className="bg-emerald-950/20 border border-emerald-800/30 rounded-lg px-3 py-2.5">
                              <div className="flex items-center gap-1.5 mb-1">
                                <span className="text-[11px] font-semibold text-emerald-300">
                                  {PIPELINE_LABELS[p] ?? p}
                                </span>
                              </div>
                              {narrative && (
                                <>
                                  <p className="text-xs text-gray-300 leading-relaxed">{narrative.why}</p>
                                  <p className="text-xs text-sky-400 mt-1">→ {narrative.signal}</p>
                                </>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <span className="text-[11px] text-slate-300">
                        Belum memenuhi threshold pipeline spesifik
                      </span>
                    )}

                    {/* Konteks Sektor: rotasi (data live) + tema struktural (opini riset) */}
                    {item.sector && (
                      <div className="bg-blue-950/20 border border-blue-800/30 rounded-lg px-3 py-2.5 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-blue-300">Konteks Sektor — {item.sector}</span>
                          {sectorRotation[item.sector] && (() => {
                            const rot = sectorRotation[item.sector];
                            const isAccumulate = rot.signal === "ACCUMULATE";
                            const isDistribute = rot.signal === "DISTRIBUTE";
                            return (
                              <div className="flex items-center gap-1.5 text-[11px]">
                                {isAccumulate ? (
                                  <><TrendingUp size={12} className="text-emerald-400" /><span className="text-emerald-400 font-medium">Rotasi Masuk</span></>
                                ) : isDistribute ? (
                                  <><TrendingDown size={12} className="text-red-400" /><span className="text-red-400 font-medium">Rotasi Keluar</span></>
                                ) : (
                                  <><Minus size={12} className="text-gray-400" /><span className="text-gray-400">Netral</span></>
                                )}
                                {rot.return_1m != null && (
                                  <span className={`ml-1 ${rot.return_1m >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                                    {rot.return_1m >= 0 ? "+" : ""}{(rot.return_1m * 100).toFixed(1)}% (1M)
                                  </span>
                                )}
                              </div>
                            );
                          })()}
                        </div>
                        {SECTOR_STRUCTURAL_THEME[item.sector] && (() => {
                          const theme = SECTOR_STRUCTURAL_THEME[item.sector];
                          return (
                            <div className="space-y-1.5 text-xs">
                              <p className="text-gray-300"><span className="text-sky-400 font-medium">Tren:</span> {theme.trend}</p>
                              <p className="text-gray-300"><span className="text-emerald-400 font-medium">Katalis:</span> {theme.catalyst}</p>
                              <p className="text-gray-400"><span className="text-amber-400 font-medium">Risiko:</span> {theme.risk}</p>
                            </div>
                          );
                        })()}
                        <p className="text-[10px] text-slate-500 italic">Rotasi: data harga aktual 90 hari. Tema: opini riset struktural, bukan sinyal trading.</p>
                      </div>
                    )}

                    {/* AI Insight — on demand */}
                    {(() => {
                      const key = item.canonical_symbol;
                      const insight = aiInsights[key];
                      const loading = aiLoading[key];
                      const rot = item.sector ? sectorRotation[item.sector] : undefined;
                      const priorityColor = insight?.research_priority === "HIGH"
                        ? "text-emerald-400" : insight?.research_priority === "MEDIUM"
                          ? "text-amber-400" : "text-gray-400";
                      return (
                        <div>
                          {!insight && (
                            <button
                              onClick={() => fetchAiInsight(item, rot)}
                              disabled={loading}
                              className="flex items-center gap-1.5 text-xs text-purple-400 hover:text-purple-300 disabled:opacity-50 transition-colors"
                            >
                              {loading
                                ? <><Loader2 size={13} className="animate-spin" />Menganalisis...</>
                                : <><Bot size={13} />Analisis AI</>}
                            </button>
                          )}
                          {insight && !insight.skipped && (
                            <div className="bg-purple-950/20 border border-purple-800/30 rounded-lg px-3 py-2.5 space-y-2">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-purple-300 flex items-center gap-1.5">
                                  <Bot size={12} /> Analisis AI
                                </span>
                                {insight.research_priority && (
                                  <span className={`text-[11px] font-medium ${priorityColor}`}>
                                    Prioritas Riset: {insight.research_priority}
                                  </span>
                                )}
                              </div>
                              {insight.investment_thesis && (
                                <p className="text-xs text-gray-200 leading-relaxed">{insight.investment_thesis}</p>
                              )}
                              {insight.sector_trend && (
                                <p className="text-xs text-sky-300"><span className="font-medium">Tren sektor:</span> {insight.sector_trend}</p>
                              )}
                              {insight.near_term_catalysts && insight.near_term_catalysts.length > 0 && (
                                <div>
                                  <p className="text-[11px] font-medium text-emerald-400 mb-1">Katalis potensial:</p>
                                  <ul className="space-y-0.5">
                                    {insight.near_term_catalysts.map((c, i) => (
                                      <li key={i} className="text-xs text-gray-300 flex gap-1.5"><span className="text-emerald-500 mt-px">•</span>{c}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {insight.key_risks && insight.key_risks.length > 0 && (
                                <div>
                                  <p className="text-[11px] font-medium text-amber-400 mb-1">Risiko kunci:</p>
                                  <ul className="space-y-0.5">
                                    {insight.key_risks.map((r, i) => (
                                      <li key={i} className="text-xs text-gray-400 flex gap-1.5"><span className="text-amber-500 mt-px">•</span>{r}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              <p className="text-[10px] text-slate-500 italic">Dihasilkan AI dari data terverifikasi. Bukan nasihat investasi.</p>
                            </div>
                          )}
                          {insight?.skipped && (
                            <p className="text-xs text-red-400">AI tidak tersedia: {insight.reason}</p>
                          )}
                        </div>
                      );
                    })()}

                    {/* Strengths & Concerns */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                      <div className="bg-emerald-950/20 border border-emerald-900/30 rounded-lg p-2.5">
                        <p className="text-emerald-400 font-medium mb-1">Faktor Pendukung</p>
                        {item.score.strengths.length > 0 ? (
                          <ul className="list-disc list-inside text-gray-300 space-y-0.5">
                            {item.score.strengths.map((s, idx) => (
                              <li key={idx}>{s}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-slate-300">Tidak ada highlight spesifik</p>
                        )}
                      </div>

                      <div className="bg-amber-950/20 border border-amber-900/30 rounded-lg p-2.5">
                        <p className="text-amber-400 font-medium mb-1">Risiko & Kontra-Argumen</p>
                        {item.score.concerns.length > 0 ? (
                          <ul className="list-disc list-inside text-gray-300 space-y-0.5">
                            {item.score.concerns.map((c, idx) => (
                              <li key={idx}>{c}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-slate-300">Periksa laporan keuangan & likuiditas</p>
                        )}
                      </div>
                    </div>

                    {/* Reverse Multibagger Scenario Toggle */}
                    {scenarios.length > 0 && (
                      <div>
                        <button
                          onClick={() =>
                            setExpandedSymbol(isExpanded ? null : item.canonical_symbol)
                          }
                          className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
                        >
                          {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                          Reverse Multibagger Scenario (Syarat EPS CAGR 2x–10x dalam 5 Tahun)
                        </button>

                        {isExpanded && (
                          <div className="mt-2 bg-gray-900/60 border border-gray-800 rounded-lg p-3 overflow-x-auto">
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="text-slate-300 border-b border-gray-800">
                                  <th className="text-left py-1.5 pr-3">Target</th>
                                  <th className="text-right py-1.5 pr-3">Horizon</th>
                                  <th className="text-right py-1.5 pr-3">
                                    Syarat EPS CAGR (PE Tetap)
                                  </th>
                                  <th className="text-right py-1.5 pr-3">
                                    Syarat EPS CAGR (Re-rating)
                                  </th>
                                  <th className="text-right py-1.5 pr-3">Asumsi Dilusi/Thn</th>
                                  <th className="text-left py-1.5">Catatan Risiko (Anti-Hype)</th>
                                </tr>
                              </thead>
                              <tbody>
                                {scenarios.map(sc => (
                                  <tr
                                    key={sc.target_multiple}
                                    className="border-b border-gray-800/40"
                                  >
                                    <td className="py-1.5 pr-3 font-semibold text-emerald-400">
                                      {sc.target_multiple}x
                                    </td>
                                    <td className="py-1.5 pr-3 text-right text-gray-400">
                                      {sc.horizon_years} thn
                                    </td>
                                    <td className="py-1.5 pr-3 text-right text-gray-200">
                                      {sc.required_eps_cagr_constant_pe_pct.toFixed(1)}%/thn
                                    </td>
                                    <td className="py-1.5 pr-3 text-right text-gray-300">
                                      {sc.required_eps_cagr_rerating_pct != null
                                        ? `${sc.required_eps_cagr_rerating_pct.toFixed(1)}%/thn`
                                        : "—"}
                                    </td>
                                    <td className="py-1.5 pr-3 text-right text-gray-400">
                                      {sc.assumed_annual_dilution_pct.toFixed(1)}%
                                    </td>
                                    <td className="py-1.5 text-gray-400">
                                      {sc.downside_risk_note}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {mbSearched && !mbLoading && filteredMbResults.length === 0 && !mbError && (
            <div className="text-center py-12 text-slate-300 space-y-2">
              <Sparkles size={28} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">Belum ada kandidat yang lolos filter Multibagger ini</p>
              <p className="text-xs text-slate-300 max-w-sm mx-auto">
                Coba turunkan Tier Minimum ke WEAK atau pilih Semua Pipeline.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
