---
description: Susun investment thesis lengkap dari semua data yang tersedia
argument-hint: "[ticker]"
---

# /thesis — Investment Thesis (Stock Intelligence)

Susun investment thesis dari data backend + AI evidence report. Ini adalah command paling komprehensif.

## Step 1: Fetch Semua Data

Panggil endpoint berikut (bisa paralel):

```
GET /api/v1/stocks/{symbol}/financial-bundle?peer_limit=8
GET /api/v1/stocks/{symbol}/analysis          ← AI recommendation engine
GET /api/v1/stocks/{symbol}/dividend           ← dividend sustainability
GET /api/v1/swing/{symbol}                     ← swing trade setup
GET /api/v1/screener/multibagger               ← (cek apakah masuk daftar)
```

## Step 2: Susun Thesis

**Bagian 1: Company Overview**
- Profil bisnis, sektor, exchange
- Kapitalisasi pasar, posisi dalam sektor

**Bagian 2: Investment Case**
Dari `analysis` endpoint:
- Signal: BUY/HOLD/SELL
- Score komposit dan breakdown per faktor
- Key strengths dan risks dari AI evidence

**Bagian 3: Valuation**
Dari `financial-bundle`:
- Trading multiples vs peers (P/E, P/B, EV/EBITDA)
- Premium/discount vs sektor median
- Upside/downside berdasarkan reversion ke median

**Bagian 4: Quality Check**
- ROE, margin, debt level vs peers
- Dividend sustainability (dari dividend endpoint)
- Untuk bank: NIM, NPL, CAR

**Bagian 5: Technical Timing**
- RSI, SMA200 positioning
- Swing trade setup jika ada
- Entry range / risk level

**Bagian 6: Catalyst & Risks**
Berikan opini berdasarkan data yang tersedia:
- Potential catalysts (earnings, macro, sector rotation)
- Key risks (valuation, macro, company-specific)

**Bagian 7: Conclusion**
- Rating: STRONG BUY / BUY / HOLD / SELL / STRONG SELL
- Target range (berdasarkan peer multiple reversion)
- Investment horizon

## Step 3: Format Output

Gunakan skill `equity-research` → `thesis` skill untuk output profesional jika diminta.

Atau sajikan langsung dalam markdown yang bersih.

## Disclaimer

Selalu sertakan: "Thesis ini dibuat dari data publik untuk tujuan riset pribadi. 
Bukan nasihat investasi. Semua keputusan investasi sepenuhnya tanggung jawab investor."
