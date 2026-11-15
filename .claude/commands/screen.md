---
description: Screen saham IDX/US berdasarkan kriteria fundamental + teknikal
argument-hint: "[opsional: kriteria, contoh: bank ROE>15 atau teknologi growth]"
---

# /screen — Stock Screener (Stock Intelligence)

Jalankan screener menggunakan backend, lalu analisis hasilnya dengan equity-research skill.

## Step 1: Parse Kriteria

Dari argumen, identifikasi:
- **Sektor**: bank, telekomunikasi, consumer, teknologi, energi, properti, dll
- **Exchange**: IDX (default), US, atau keduanya
- **Metrik kuantitatif**: ROE, P/E, margin, div yield, dll

Contoh interpretasi:
- "bank ROE>15" → sektor Banking, IDX, ROE > 15%
- "teknologi growth" → sektor Technology, semua exchange, growth bias
- "dividend yield>4" → semua sektor, dividend_yield > 4%

## Step 2: Fetch Data Screener

```
GET /api/v1/screener/multibagger
```

Response berisi daftar saham dengan skor STRONG/MODERATE/WEAK/NOT_QUALIFIED.

Filter berdasarkan kriteria user dari response.

## Step 3: Fetch Detail Top 5

Untuk 5 saham terbaik dari hasil screener:
```
GET /api/v1/stocks/{symbol}/financial-bundle
```

## Step 4: Gunakan Skill equity-research → screen

Gunakan `screen` skill dari equity-research plugin dengan data yang sudah dikumpulkan untuk presentasi yang lebih baik.

## Step 5: Output

```
HASIL SCREENER: {kriteria}
{N} saham ditemukan dari {total} yang dianalisis

TOP PICKS:
1. {symbol} — {company_name}
   Score: {tier} | P/E: {pe}x | ROE: {roe}% | Div: {div}%
   
2. ...

FILTER AKTIF:
- Exchange: {IDX/US/ALL}
- Sektor: {sector}
- Kriteria tambahan: {metrik}
```
