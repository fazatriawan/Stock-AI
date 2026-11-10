# ARCHITECTURE DECISIONS — Stock Intelligence
**Dibuat:** 4 November 2026  
**Berdasarkan:** PRD v1.7.1 + inspeksi langsung codebase

Setiap keputusan diberi status: **KEEP** (pertahankan), **MODIFY** (perlu perbaikan), **DEFER** (tunda sampai fase tertentu).

---

## Stack & Framework

### ADR-01 — Next.js 14 App Router + FastAPI
**Status: KEEP**  
Stack ini sudah ada dan konsisten. App Router dipakai di semua 17 halaman. Tidak ada alasan teknis untuk migrasi ke framework lain.  
**Anti-regresi:** jangan tambah Express/Nest.js atau Flask di samping FastAPI.

### ADR-02 — SQLAlchemy async + PostgreSQL prod / SQLite test
**Status: KEEP**  
`session.py` sudah deteksi SQLite vs PostgreSQL untuk skip `pool_size`/`max_overflow`. Integration tests jalan di-memory SQLite. Arsitektur ini solid.  
**Catatan:** pastikan `alembic upgrade` hanya dijalankan terhadap PostgreSQL; SQLite untuk test saja.

### ADR-03 — Pydantic v2 + `from __future__ import annotations`
**Status: KEEP**  
Sudah dipasang di semua route files untuk Python 3.9 compatibility. `eval_type_backport` di requirements. Jangan hapus `from __future__ import annotations`.

### ADR-04 — Provider pattern (`MarketDataProvider` protocol)
**Status: KEEP**  
`providers/base.py` mendefinisikan `Protocol` yang harus diimplementasikan semua provider. `registry.py` untuk dependency injection.  
**Yang harus dimodifikasi:** registry saat ini selalu return mock; perlu logika switching berdasarkan `Settings.yfinance_enabled`.

---

## Data & Storage

### ADR-05 — `canonical_symbol` format `EXCHANGE:TICKER`
**Status: KEEP**  
Format `IDX:BBCA`, `US:AAPL` dipakai konsisten di models, routes, frontend. Konversi ke yfinance suffix (`.JK`) di `yfinance_provider.py`. Tidak boleh ada ticker tanpa prefix exchange di boundary API.

### ADR-06 — Immutable price bars & macro observations
**Status: KEEP**  
`PriceBar` dan `MacroObservation` tidak punya `updated_at` by design (PRD §15). Koreksi dilakukan dengan revision record baru, bukan update in-place.

### ADR-07 — Alembic untuk semua schema changes
**Status: MODIFY**  
Saat ini ada 25+ tabel di `models.py` tapi hanya 2 migration file. **Wajib dibuat initial migration** sebelum deploy ke DB manapun. Urutan: backup → `alembic revision --autogenerate -m "000_initial_schema"` → review diff → apply.

### ADR-08 — `FinancialFact` sebagai EAV untuk fundamental data
**Status: KEEP dengan catatan**  
EAV (entity-attribute-value) di `financial_facts` fleksibel untuk berbagai metrik lintas sektor. Tradeoff: query lebih kompleks. Cukup untuk pilot; bisa dioptimasi ke kolom-kolom konkret per sektor di R8+.  
**Yang perlu ditambah:** `data_quality` enum (`VERIFIED/ESTIMATED/RESTATED`) dan `integrity_flag` boolean.

---

## Decision Engine

### ADR-09 — Rule-based engine deterministik, bukan LLM scoring
**Status: KEEP (non-negotiable)**  
PRD §4 mewajibkan: "Nilai kuantitatif selalu dari calculation engine; Claude hanya sintesis." LLM tidak boleh mengubah `Action` atau skor dari engine.  
**Anti-regresi:** jangan tambah LLM call di dalam `decisions/engine.py`.

### ADR-10 — `HardGateStatus` sebagai veto sebelum ranking
**Status: KEEP**  
Gate `FAIL_STALE_PRICE`, `FAIL_NO_FUNDAMENTAL`, dll. harus tetap sebagai hard veto — tidak bisa di-override oleh skor tinggi. PRD §12 HARD-01 menambah gate baru: `FAIL_LIQUIDITY`, `FAIL_LOT_SIZE`.

### ADR-11 — IPS parameters hardcoded di `DecisionConfig`
**Status: MODIFY (P0)**  
`max_position_weight = 0.10` dan `max_sector_weight = 0.30` harus dipindah ke tabel DB `investment_policies` yang bisa diedit user. Lihat BL-05 di PRIORITY_EXECUTION_BOARD.md.

---

## API Design

### ADR-12 — DELETE endpoints return 204 + `response_class=Response`
**Status: KEEP**  
Pattern yang sudah distandardisasi setelah bug di sesi sebelumnya. Semua DELETE route pakai `@router.delete(..., response_class=Response)` dan `return Response(status_code=204)`.

### ADR-13 — `ErrorEnvelope` untuk semua error response
**Status: KEEP**  
`app/core/exceptions.py` mendefinisikan format error standar. Jangan return raw string untuk error di boundary API.

### ADR-14 — Prefix `/api/v1/` untuk semua routes
**Status: KEEP**  
Semua route di-include dengan prefix ini di `main.py`. Frontend `api.ts` sudah menggunakan `API_BASE/api/v1`.

---

## Security

### ADR-15 — Server-side credentials only
**Status: KEEP (non-negotiable)**  
Semua API keys (Anthropic, FMP, FRED, BPS) hanya di `.env` server-side. Tidak ada credentials yang masuk ke frontend bundle atau response API.

### ADR-16 — Tidak ada order execution routes
**Status: KEEP (non-negotiable)**  
PRD melarang keras. Tidak boleh ada endpoint yang mengirim order ke broker. Semua "rekomendasi" adalah research output, bukan instruksi trading.

### ADR-17 — Single-user, local-first deployment
**Status: KEEP**  
App didesain untuk satu pemilik. Auth layer minimal (session-based) cukup untuk personal use. Tidak perlu multi-tenant.

---

## Deferred Decisions

### ADR-18 — DuckDB/Parquet untuk backtesting scale
**Status: DEFER (R18)**  
PRD menyebut Parquet/DuckDB "only when backtest scale justifies." Saat ini PostgreSQL cukup. Evaluasi lagi saat dataset > 10 tahun × 500 instrumen.

### ADR-19 — Redis caching strategy
**Status: DEFER (R13)**  
Redis sudah di docker-compose tapi belum dipakai di kode. Aktifkan saat R13 (provider operations hardening) untuk cache harga & fundamentals.

### ADR-20 — Sectors Financial API v2 adapter
**Status: DEFER (R8)**  
Butuh API key yang valid dan audit endpoint yang tersedia. Jangan build adapter sebelum key terverifikasi dan entitlement diketahui.
