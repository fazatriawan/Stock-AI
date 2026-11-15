---
description: DCF valuation model menggunakan data backend stock-intelligence
argument-hint: "[ticker] [opsional: skenario konservatif|base|agresif]"
---

# /dcf — DCF Valuation (Stock Intelligence)

Bangun model DCF menggunakan data dari backend lokal + peer comps sebagai benchmark, lalu gunakan skill `dcf-model` untuk output institusional.

## Step 1: Resolve Symbol

Ambil ticker dari argumen. Jika tidak ada, tanya.
Normalisasi: `BBCA` → `IDX:BBCA`, `AAPL` → `US:AAPL`

## Step 2: Fetch Data

Panggil dua endpoint secara bersamaan:

```
GET /api/v1/stocks/{symbol}/financial-bundle?peer_limit=6
GET /api/v1/stocks/{symbol}/prices?range=5y&adjusted=true
```

Dari **financial-bundle**:
- Gunakan `revenue_ttm`, `ebitda_ttm`, `net_income_ttm` sebagai titik awal proyeksi
- Gunakan `gross_margin`, `operating_margin` sebagai base margin
- Gunakan `debt_to_equity` untuk estimasi kapital struktur
- Gunakan peer data untuk benchmark: `sector_median_pe`, `ev_ebitda`

Dari **prices** (array `bars`):
- Hitung historical revenue growth jika ada (dari EPS trend)
- Gunakan volatilitas harga sebagai proxy beta untuk WACC

## Step 3: Asumsi DCF

Susun asumsi dari data yang ada:

**Revenue Growth (3 skenario):**
- Bear: pertumbuhan 50% di bawah rata-rata peer
- Base: pertumbuhan sesuai median sektor (atau historis 3y)
- Bull: pertumbuhan 1.5x rata-rata peer

**Margin:**
- Target margin terminal = median sektor (dari `sector_median_roe` / peers)
- Gunakan `operating_margin` aktual sebagai titik awal

**WACC (estimasi sederhana untuk IDX):**
- Risk-free rate: gunakan BI Rate saat ini (~6% untuk IDX) atau UST 10y (~4.5% untuk US)
- Equity risk premium: Indonesia ~7%, US ~5%
- Beta: estimasi dari volatilitas harga (atau gunakan 1.0 jika tidak tersedia)
- Formula: WACC = Rf + β × ERP + cost_of_debt × (1-tax) × D/(D+E)

**Terminal Value:**
- Exit multiple: gunakan `sector_median_pe` atau `ev_ebitda` dari peer comps
- Terminal growth: 3-5% untuk IDX (GDP growth Indonesia)

## Step 4: Jalankan Skill dcf-model

Gunakan skill `dcf-model` dengan asumsi yang sudah dihitung untuk:
1. Proyeksi 5-10 tahun (Bear/Base/Bull)
2. WACC calculation table
3. Terminal value via exit multiple (benchmark dari comps)
4. Sensitivitas: WACC vs terminal growth rate
5. Implied share price vs harga saat ini (`last_price` dari bundle)
6. Cross-check: DCF implied P/E vs `sector_median_pe`

## Step 5: Output

```
RINGKASAN VALUASI: {company_name} ({canonical_symbol})

Harga Saat Ini: {last_price} {currency}
52W High/Low: {high_52w} / {low_52w}

Peer Comps Benchmark:
- Median P/E Sektor: {sector_median_pe}x
- Median EV/EBITDA: {ev_ebitda_median}x

DCF Base Case:
- Implied Harga: Rp/$ XXX
- Upside/Downside vs Harga Saat Ini: +/-XX%
- Terminal Value sebagai % EV: XX%

WACC Assumptions:
- Risk-free rate: X%
- Beta: X.X
- Cost of equity: X%
- WACC: X%
```

## Catatan IDX

- Mata uang IDR: konversi ke Miliar IDR untuk readability  
- BI Rate terkini adalah acuan risk-free rate (bukan UST)
- Terminal growth sesuai proyeksi GDP Indonesia (BPS)
- Data bersumber dari Stock Intelligence backend — bukan proyeksi analis
- **DISCLAIMER**: DCF ini untuk riset pribadi, bukan rekomendasi investasi
