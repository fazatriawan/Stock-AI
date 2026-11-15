---
description: Analisis kinerja keuangan kuartalan dari data backend
argument-hint: "[ticker] [opsional: Q1/Q2/Q3/Q4 YYYY]"
---

# /earnings — Earnings Analysis (Stock Intelligence)

Analisis kinerja keuangan terbaru dari data backend, bandingkan dengan periode sebelumnya dan ekspektasi sektor.

## Step 1: Input

Ambil ticker dan kuartal dari argumen. Jika tidak ada:
- Tanya ticker
- Default: data terbaru yang tersedia

## Step 2: Fetch Data

```
GET /api/v1/stocks/{symbol}/financial-bundle?peer_limit=5
GET /api/v1/stocks/{symbol}/overview
```

Dari **financial-bundle**:
- `revenue_ttm`, `net_income_ttm`, `gross_margin`, `operating_margin`
- `pe_ratio`, `pb_ratio`, `roe`
- `data_period` → menunjukkan periode data terbaru
- Peer comparison untuk konteks relatif

Dari **overview**:
- `fundamental` → semua metrik keuangan snapshot
- `technical` → sinyal teknikal untuk konteks

## Step 3: Analisis

**Beat/Miss terhadap Sektor:**
- Bandingkan margin aktual vs `sector_median` dari peers
- Bandingkan P/E vs `sector_median_pe` (premium/discount berapa %)
- Bandingkan ROE vs `sector_median_roe`

**Trend Analysis:**
Karena kita tidak punya data kuartalan historis per saham secara langsung, jelaskan:
- Posisi metrik saat ini vs peer median
- Apakah valuasi premium atau discount vs sektor
- Sinyal teknikal: RSI, posisi vs SMA200

**Untuk Bank IDX:**
- NIM vs rata-rata industri (~5-6% untuk bank besar IDX)
- NPL Gross (healthy < 3%)
- CAR (minimum 8% per OJK, strong > 15%)
- ROE vs peer (bank besar IDX biasanya 15-25%)

## Step 4: Gunakan Skill earnings-analysis (Opsional)

Jika user ingin laporan DOCX formal (untuk bank, biasanya laporan tahunan):
Gunakan skill `earnings-analysis` dengan data yang sudah dikumpulkan.

## Step 5: Output Ringkasan

```
EARNINGS SNAPSHOT: {company_name} ({canonical_symbol})
Data Period: {data_period}

KINERJA vs SEKTOR:
├── P/E: {pe_ratio}x vs median {sector_median_pe}x ({premium/discount}%)
├── P/B: {pb_ratio}x vs median {sector_median_pb}x  
├── ROE: {roe}% vs median {sector_median_roe}%
└── Gross Margin: {gross_margin}% vs avg peers

METRIK KEUANGAN TTM:
├── Revenue: Rp/$ {revenue_ttm}
├── Net Income: Rp/$ {net_income_ttm}
├── Operating Margin: {operating_margin}%
└── Net Margin: {net_margin}%

[BANK ONLY]
├── NIM: {nim}%
├── NPL Gross: {npl_gross}%
└── CAR: {car}%

TEKNIKAL:
├── Harga: {last_price} | 52W: {low_52w} - {high_52w}
├── RSI-14: {rsi_14}
└── vs SMA200: {above_sma_200 ? 'Di atas' : 'Di bawah'}

PEER RANKING:
{tabel singkat 5 peers diurutkan berdasar market_cap}
```

## Catatan

- Data dari yfinance + Sectors Financial API (bukan Bloomberg/Reuters)
- Tidak ada data konsensus analis — bandingkan vs peer median sebagai proxy
- Untuk data lebih detail, gunakan EDGAR/IDX e-reporting langsung
