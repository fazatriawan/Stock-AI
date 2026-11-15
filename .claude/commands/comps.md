---
description: Comparable company analysis menggunakan data backend stock-intelligence
argument-hint: "[ticker, misal: BBCA atau IDX:BBCA]"
---

# /comps — Analisis Peer Comps (Stock Intelligence)

Jalankan comparable company analysis menggunakan data dari backend lokal, lalu gunakan skill `comps-analysis` untuk memformat hasilnya.

## Step 1: Resolve Symbol

Ambil argumen ticker dari input. Jika tidak ada, tanya:
- "Ticker mana yang ingin dianalisis? (contoh: BBCA, TLKM, BBRI)"

Normalisasi: jika hanya ticker tanpa exchange prefix, coba `IDX:{ticker}` untuk saham Indonesia, `US:{ticker}` untuk saham AS.

## Step 2: Fetch Data dari Backend

Panggil endpoint berikut (backend lokal di `http://localhost:8000/api/v1`):

```
GET /api/v1/stocks/{symbol}/financial-bundle?peer_limit=8
```

Contoh: `GET /api/v1/stocks/IDX:BBCA/financial-bundle?peer_limit=8`

Data yang dikembalikan:
- `canonical_symbol`, `company_name`, `exchange`, `sector`, `currency`
- `last_price`, `market_cap`, `enterprise_value`
- `revenue_ttm`, `ebitda_ttm`, `net_income_ttm`
- `gross_margin`, `operating_margin`, `net_margin`
- `pe_ratio`, `pb_ratio`, `ev_ebitda`, `dividend_yield`
- `roe`, `debt_to_equity`
- `peers[]` — daftar peer se-sektor dengan metrik yang sama
- `sector_median_pe`, `sector_median_pb`, `sector_median_roe`
- `nim`, `npl_gross`, `car` — khusus bank

Jika endpoint mengembalikan 404: simbol tidak ditemukan di database. Minta user untuk menjalankan setup data di `/settings` terlebih dahulu.

## Step 3: Format Data untuk Comps Table

Dari response, susun tabel comps dengan kolom:

**Operating Statistics:**
- Company | Revenue (TTM) | Gross Margin | Operating Margin | Net Margin | ROE | D/E

**Valuation Multiples:**
- Company | Market Cap | EV | P/E | P/B | EV/EBITDA | Div Yield

Tandai subject company (is_subject: true) dengan bintang (*) atau bold.
Hitung statistik: Median, 75th pct, 25th pct dari peers.

**Untuk saham perbankan** (jika `nim` atau `npl_gross` ada di response):
Tambahkan kolom: NIM | NPL Gross | CAR

**Currency note**: Tampilkan angka dalam currency lokal (IDR untuk IDX, USD untuk US).
- Market cap IDR: tampilkan dalam Triliun (÷1e12)
- Revenue IDR: tampilkan dalam Miliar (÷1e9) atau Triliun

## Step 4: Jalankan Skill comps-analysis

Gunakan skill `comps-analysis` dengan data yang sudah di-fetch untuk:
1. Validasi peer group (4-8 perusahaan sebanding)
2. Buat Excel output dengan format institusional
3. Tambahkan statistical summary (Max, 75th, Median, 25th, Min)
4. Dokumentasikan sumber data: "Stock Intelligence backend (yfinance + Sectors Financial API)"

## Step 5: Output

Berikan:
1. **Ringkasan tabel** di chat (plain text atau markdown)
2. **Insight utama**: siapa yang trade at premium/discount vs peers
3. **Excel file** (.xlsx) via skill comps-analysis jika diminta

## Catatan Khusus IDX

- Tahun fiskal mayoritas emiten IDX: Desember (Q4 = full year)
- Market cap dalam IDR — convert ke Miliar IDR untuk readability
- Peer biasanya di-filter per exchange (IDX vs NYSE/NASDAQ terpisah)
- Untuk bank: gunakan NIM, NPL, CAR sebagai pengganti gross margin
- Data bersumber dari yfinance + Sectors Financial API (bukan Bloomberg/FactSet)
