# IMPLEMENTATION AUDIT — Stock Intelligence
**Dibuat:** 4 November 2026  
**Berdasarkan:** PRD v1.7.1 + inspeksi langsung codebase  
**Metode:** baca source, models, routes, tests, config — tidak berasumsi dari nama folder

---

## Ringkasan Status

| Kategori | Jumlah | Catatan |
|---|---|---|
| EXISTING_VERIFIED | 24 | Kode ada, test ada, fungsional |
| PARTIAL | 11 | Ada tapi tidak lengkap / data masih mock |
| MISSING | 18 | Belum dibuat sama sekali |
| BLOCKED_LIVE | 5 | Butuh kredensial / API key eksternal |

---

## Matriks Requirement

### DATA — Data Platform & Instrument Master

| Req ID | Feature | Status | Evidence | Masalah |
|---|---|---|---|---|
| DATA-01 | Canonical instrument registry | PARTIAL | `app/db/models.py:Instrument`, `InstrumentAlias` | Alias tersimpan di DB tapi tidak ada endpoint `GET /instruments/{alias}` → lookup cross-exchange; migration belum di Alembic (hanya ada 2 migration files untuk journal+notes) |
| DATA-02 | Market prices OHLCV | PARTIAL | `PriceBar` model, `yfinance_provider.py`, `mock_provider.py` | yfinance berjalan tapi tidak ada circuit breaker; tidak ada fallback label `DEMO/DELAYED`; `adj_close` bisa None tanpa UI warning |
| DATA-03 | Fundamentals by sector | PARTIAL | `FinancialFact` model, `analytics/fundamental.py` | Data dari mock only; tidak ada adapter Sectors API v2; bank vs non-bank logic partial di `fundamental.py` |
| DATA-04 | Provenance & bitemporal | PARTIAL | `Source` model, `available_at` di `FinancialFact` | `available_at` ada di schema tapi tidak di-populate oleh provider; tidak ada `retrieved_at` di `Source` |
| DATA-05 | Provider adapter & health | EXISTING_VERIFIED | `providers/base.py` protocol, `registry.py`, `data_health.py` route | ProviderStatus OK/DEGRADED/DOWN ada; circuit breaker belum ada |
| DATA-06 | Financial Integrity Checker | MISSING | — | Belum ada. Validasi EPS vs shares, unit IDR, balance sheet cross-check tidak ada di manapun |
| DATA-07 | Sectors API v2 | BLOCKED_LIVE | `fmp_enabled: bool = False` di config | FMP key diset tapi disabled; Sectors Financial API v2 (IDX) belum ada adapter |

### PORT — Portfolio & Broker Integration

| Req ID | Feature | Status | Evidence | Masalah |
|---|---|---|---|---|
| PORT-01 | Immutable transaction ledger | EXISTING_VERIFIED | `Trade` model (immutable design), `portfolio/calculator.py` WAC, `import_trades.py`, fingerprint dedup | Soft-delete belum ada (delete route menghapus langsung); FX trade belum ditest |
| PORT-02 | Portfolio valuation | EXISTING_VERIFIED | `portfolio/calculator.py`, `portfolio.py` route | TWR/XIRR belum ada; hanya unrealized P/L; dividen cashflow model ada tapi tidak masuk kalkulasi |
| PORT-03 | Import & reconciliation | PARTIAL | `importers/csv_importer.py`, `xlsx_importer.py`, `pdf_importer.py`, `fingerprint.py` | PDF parser ada tapi belum ditest dengan format Stockbit nyata; preview→confirm flow ada; KSEI reconciliation belum ada |
| PORT-04 | Gmail read-only sync | MISSING | Sidebar stub hanya di frontend | OAuth belum ada; sesuai PRD ini P2 dan butuh kredensial |
| PORT-05 | Portfolio risk & simulations | PARTIAL | `portfolio/simulator.py`, `portfolio/analyzer.py`, `rebalance.py` route | Concentration check ada; correlation/beta belum ada; what-if partial |
| PORT-06 | Loss position analyzer | PARTIAL | `portfolio_intelligence.py` route, `analyzer.py` | Frontend ada di `/portfolio/loss`; diagnostic categories ada tapi deterministic (tidak ada data nyata) |

### ANL — Analytics & Decision Engines

| Req ID | Feature | Status | Evidence | Masalah |
|---|---|---|---|---|
| ANL-01 | Fundamental research | PARTIAL | `analytics/fundamental.py` | Metrik tersedia tapi semua dari mock; bank-specific (NIM, NPL, CAR) ada secara schema, belum dari data nyata |
| ANL-02 | Valuation & scenarios | PARTIAL | `decisions/engine.py` FactorScores.valuation | PE/PB tersedia tapi dari mock; DCF/dividend-discount belum ada |
| ANL-03 | Technical & market regime | EXISTING_VERIFIED | `analytics/technical.py` SMA/EMA/RSI/MACD/ATR | Kalkulasi deterministik dari price_bars; market regime belum ada |
| ANL-04 | Multi-factor decision engine | EXISTING_VERIFIED | `decisions/engine.py`, 7 faktor, HardGate, Action enum | Rule-based deterministik; version tidak di-persist ke `AnalysisRun`; `NO_ACTION` ada |
| ANL-05 | Peer & sector intelligence | MISSING | screener.py ada tapi peer comparison belum ada | Screener filter ada; peer relative valuation tidak ada |
| ANL-06 | Research thesis & AI critic | PARTIAL | `ai/adapter.py`, `reporting/` | AI adapter ada tapi critic/claim verifier belum ada; EvidenceBundle format partial |

### STRAT — Strategy & Goals

| Req ID | Feature | Status | Evidence | Masalah |
|---|---|---|---|---|
| STRAT-01 | Goals and strategy fit | MISSING | Frontend `/settings` ada tapi tidak connect ke backend | Tidak ada DB table untuk goals/buckets; tidak ada strategy routing |
| STRAT-02 | Capital preservation | MISSING | — | Real-return calculator belum ada; SBN comparison belum ada |
| STRAT-03 | Dividend sustainability | MISSING | `DividendCashflow` model ada di DB | Tidak ada route/logic untuk dividend sustainability analysis |
| STRAT-04 | Swing/paper trading | MISSING | — | P3; belum dikerjakan |

### OWN — Ownership & Insider

| Req ID | Feature | Status | Evidence | Masalah |
|---|---|---|---|---|
| OWN-01 | Filings & ownership graph | MISSING | `OwnershipFact` model ada | Tidak ada route, adapter, atau frontend |
| OWN-02 | Insider & money flow | MISSING | — | P2; belum dikerjakan |
| OWN-03 | Owner track record | MISSING | — | P3; belum dikerjakan |
| OWN-04 | Governance risk | MISSING | — | P2; belum dikerjakan |

### GLOBAL — Macro & Trade

| Req ID | Feature | Status | Evidence | Masalah |
|---|---|---|---|---|
| GLOBAL-01 | Macro & policy states | PARTIAL | `MacroObservation`, `Event` models; `macro.py` route; frontend `/macro` | Manual entry saja; tidak ada ingestion dari FRED/BI; policy_stage ada |
| GLOBAL-02 | Global trade time series | MISSING | — | P2; UN Comtrade adapter belum ada |
| GLOBAL-03 | Exposure graph | MISSING | `EventCompanyImpact` model ada | Tidak ada route/logic untuk graph traversal |
| GLOBAL-04 | Global trend alerts | MISSING | — | P3 |

### HARD — Reliability & Decision Hardening (v1.7.1)

| Req ID | Feature | Status | Evidence | Masalah |
|---|---|---|---|---|
| HARD-01 | Trade Feasibility Engine | MISSING | — | P0 menurut PRD v1.7.1; belum ada lot check, ADV, spread validation |
| HARD-02 | Catalyst & Event Calendar | PARTIAL | `Event` model, manual entry di `/macro` | Tidak ada dedup; tidak ada confirmed vs estimated flag per event; tidak ada upcoming calendar view |
| HARD-03 | Personal IPS controls | MISSING | Partial di `DecisionConfig.max_position_weight` hardcoded | Tidak ada user-editable IPS; bucket goals belum ada; policy version tidak disimpan |
| HARD-04 | Financial Integrity Checker | MISSING | — | Sama dengan DATA-06; tidak ada di manapun |
| HARD-05 | Decision Attribution | MISSING | — | P2; belum dikerjakan |
| HARD-06 | Backup & restore | MISSING | — | Tidak ada backup job; tidak ada restore test; tidak ada encrypted dump |

### Infrastructure

| Item | Status | Evidence | Masalah |
|---|---|---|---|
| Docker Compose | EXISTING_VERIFIED | `docker-compose.yml` lengkap dengan db/redis/api/web | Belum ditest end-to-end; tidak ada `--env-file` yang aman |
| .env.example | MISSING | Tidak ada file ini | Onboarding baru tidak tahu variabel apa yang dibutuhkan |
| Alembic migrations | PARTIAL | 2 file migration (001, 002) | Skema DB yang ada di `models.py` jauh lebih besar dari 2 migration ini; initial migration tidak ada |
| Integration tests | EXISTING_VERIFIED | `tests/integration/test_routes_smoke.py` 18 tests | Hanya smoke tests; tidak ada golden tests untuk portfolio math |
| Unit tests | PARTIAL | 8 unit test files | `test_importers.py` belum lengkap; tidak ada test untuk `financial_integrity` |
| CI/CD | MISSING | Tidak ada `.github/workflows/` atau pipeline config | — |
| Secrets management | PARTIAL | `pydantic_settings` dari `.env` | `.env.example` tidak ada; `secret_key = "change-me"` default berbahaya |

---

## 5 Masalah Kritis Sebelum AI Bisa Memberikan Analisis Andal

1. **Semua data adalah mock/synthetic** — `mock_provider.py` default; yfinance tersedia tapi tidak dipakai di production route. Setiap angka yang ditampilkan bukan data pasar nyata. App tidak bisa dipakai untuk riset nyata sampai minimal yfinance diaktifkan dan data di-seed.

2. **Financial Integrity Checker belum ada** — tidak ada yang memvalidasi EPS vs shares, satuan IDR (ribuan/jutaan/miliar), atau cross-field consistency. EPS dari mock bisa saja salah satu satuan dan tidak ada yang menolaknya.

3. **IPS / Risk gates hardcoded** — `max_position_weight = 0.10` dan `max_sector_weight = 0.30` di `engine.py` tidak bisa diubah pengguna. PRD mewajibkan user-editable IPS sebagai P0.

4. **Alembic migrations tidak mencerminkan model** — ada 25+ tabel di `models.py` tapi hanya 2 migration file. `alembic upgrade head` pada DB kosong akan gagal karena tidak ada initial migration yang membuat tabel-tabel inti.

5. **.env.example tidak ada** — `secret_key` default adalah `"change-me"`. Siapapun yang clone repo tidak tahu konfigurasi minimal yang dibutuhkan untuk menjalankan app dengan aman.
