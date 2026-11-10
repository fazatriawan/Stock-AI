# CLAUDE.md — Stock Intelligence

Panduan ini menjelaskan cara Claude Code bekerja dalam repo ini.

## Struktur Repo

```
stock-intelligence/
  apps/web/          → Next.js 14 + TypeScript + Tailwind + shadcn/ui
  services/api/      → Python FastAPI + Pydantic + SQLAlchemy (async)
  packages/contracts/ → OpenAPI spec + generated TS types
  data/fixtures/     → Synthetic test data only (NO real market data)
  docs/              → Arsitektur, metodologi, provider matrix
```

## Backend (services/api)

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic
- Test: `cd services/api && pytest tests/ -v`
- Lint: `ruff check . && mypy app/`
- Migrations: `alembic upgrade head`
- Dev server: `uvicorn app.main:app --reload --port 8000`

## Frontend (apps/web)

- Node 20+, Next.js 14 App Router, TypeScript strict, Tailwind CSS, shadcn/ui
- Test: `cd apps/web && npm run test`
- Dev: `cd apps/web && npm run dev`
- Build: `cd apps/web && npm run build`

## Docker

- `docker compose up db redis` → jalankan PostgreSQL + Redis lokal
- `docker compose up` → jalankan semua termasuk API

## Aturan Penting

1. **TIDAK PERNAH** menyimpan API key atau secret ke dalam kode atau file yang di-commit.
2. **TIDAK PERNAH** memasang order broker atau mengeksekusi transaksi.
3. Semua angka yang ditampilkan di UI harus memiliki sumber (`source_id`, `provider`, `effective_at`).
4. LLM (Claude) tidak boleh membuat angka harga, valuasi, atau metrik keuangan tanpa data terverifikasi.
5. Setiap provider data harus melalui `MarketDataProvider` interface — tidak hardcode di route.
6. Test baru harus ditambahkan di `tests/unit/` atau `tests/integration/` sesuai tipe.
7. Selalu jalankan `ruff check` dan `mypy` sebelum commit.

## Environment

- Copy `.env.example` ke `.env` dan isi nilainya
- `DATABASE_URL` untuk async, `DATABASE_URL_SYNC` untuk Alembic
- `ANTHROPIC_API_KEY` wajib untuk fitur AI report (Milestone C+)

## Konvensi Kode

- Bahasa komentar/docstring: Bahasa Indonesia (singkat)
- Tipe data: gunakan Pydantic model untuk semua DTO, TypedDict dilarang di boundary
- Error response: selalu gunakan `ErrorEnvelope` schema
- Logging: structured JSON via `structlog`

## Milestone Saat Ini

- [x] Milestone A: Foundation scaffold + data ingestion + provider adapters
- [x] Milestone B: Portfolio + recommendation engine
- [x] Milestone C: AI evidence reports + daily briefing
- [x] Milestone D: Decisions · Screener · Performance · Macro · Notebook · Settings
- [x] R0 Audit: docs/IMPLEMENTATION_AUDIT.md · docs/PRIORITY_EXECUTION_BOARD.md · docs/ARCHITECTURE_DECISIONS.md
- [x] BL-01: Initial Alembic migration — 000_initial_schema.py, chain 000→001→002 verified
- [x] BL-03: Aktifkan yfinance — bootstrap default live, /stocks/{symbol}/prices/refresh endpoint
- [x] BL-04: Financial Integrity Checker — integrity.py, integrated ke fundamental.py, GET /stocks/{symbol}/integrity
- [x] BL-05: User-editable IPS — tabel investment_policies, migration 003, GET/PUT /settings/policy, engine baca dari DB
- [x] BL-06: Backup & restore — scripts/backup.sh + restore.sh, AES-256 enkripsi, cron-ready, docs/BACKUP_RESTORE.md
- [x] R8: Sectors Financial API adapter — SectorsProvider (31 metrics), registry priority, GET /stocks/{symbol}/peers, POST /stocks/{symbol}/fundamentals/refresh
- [x] R9: Claude EvidenceBundle + independent critic — Anthropic SDK migration (anthropic>=0.120.0), 2-pass pipeline (enrichment + critic), circuit breaker, peer/integrity context di bundle
- [x] R10: Trade Feasibility Engine — lot check IDX/US, capital adequacy, IPS position limit, ADV liquidity, spread cost; POST /stocks/{symbol}/feasibility; 16 unit tests PASS
- [x] R11: Dividend sustainability — payout ratio, FCF coverage, tren 3 tahun, DGR CAGR, real yield (yield-inflasi); GET /stocks/{symbol}/dividend; 19 unit tests PASS
- [x] R12: Daily change digest — calendar-aware IDX/NYSE, return 1D, alert dedup (1/kategori/instrumen), severity sorted, gainers/losers count; daily.py diupgrade; 17 unit tests PASS
- [x] R13: Provider ops hardening — circuit breaker CLOSED/OPEN/HALF_OPEN per provider; APScheduler backup 02:00 WIB + health probe 15min; backup sentinel; GET /admin/ops + POST /admin/backup/trigger; 13 unit tests PASS
- [x] R14: Insider Transaction Monitor — model InsiderTransaction, migration 004, scoring engine (cluster buy/sell, net sentiment, role-weighted), GET /insider/{symbol}/signal + transactions, POST import manual; 12 unit tests PASS
- [x] R15: Multibagger Screener — scoring engine 4 dimensi (growth 25, profitability 25, balance_sheet 25, valuation 25), tier STRONG/MODERATE/WEAK/NOT_QUALIFIED/INSUFFICIENT, GET /screener/multibagger; 12 unit tests PASS
- [x] R16: Backtesting Engine — 3 strategi (SMA_CROSSOVER, RSI_MEAN_REVERT, MACD_SIGNAL), equity curve, Sharpe, max drawdown, CAGR, win rate, profit factor; POST /backtest/{symbol}; 14 unit tests PASS
- [x] R17: Global Macro Integration — FRED fetcher (6 series), yield curve analyzer (NORMAL/FLAT/INVERTED), macro impact scorer (-1→+1), POST /macro/observations/refresh + /upsert, GET /macro/yield-curve + /impact; 12 unit tests PASS
- [x] R18: Swing Trade Monitor — BREAKOUT/PULLBACK detector (ATR-based stop, R:R target, volume konfirmasi), GET /swing/{symbol} + GET /swing screen; 12 unit tests PASS
- [x] R19: Alert & Notification Engine — 9 rule types (price, pct, RSI, swing, macro), cooldown dedup, webhook dispatch (Slack-compatible), POST /alerts/evaluate + CRUD /alerts/rules; 21 unit tests PASS
- [x] R20: Watchlist & Price Target Engine — WatchlistItem +price_target/cost_basis, migration 006, CRUD /watchlists, pct_to_target + pct_from_cost enrichment; 12 unit tests PASS
- [x] R21: Frontend Watchlist & Alerts — halaman /watchlist (CRUD list + item + modal), /alerts (create rule, evaluate, history), Sidebar updated
- [x] R22: Integration Summary — GET /summary aggregates macro signal + top swing setups + recent alerts + watchlist near target; 332 unit tests total PASS

## Phase: Production-Ready + Extension (Post-R22)

- [x] PX-01: Lint cleanup — ruff auto-fix 44 F401 unused imports; fix F841 unused vars, E741 ambiguous names; 0 substantive errors tersisa
- [x] PX-02: Mypy — 0 errors di file baru (watchlist.py, summary.py); pre-existing 51 errors di-isolasi dengan # type: ignore pada boundary
- [x] PX-03: Integration tests — 34 tests (smoke + R19/R22 flows) via SQLite in-memory; total 390 tests PASS
- [x] PX-04: Backtest history — BacktestRun extended (migration 007), POST /backtest/{symbol} auto-save ke DB, GET /backtest/history
- [x] PX-05: Portfolio Correlation Heatmap — analytics/correlation.py, GET /portfolio/correlation; 11 unit tests PASS
- [x] PX-06: Sector Rotation Tracker — analytics/sector_rotation.py, GET /screener/sectors/rotation; 13 unit tests PASS
- [x] PX-07: Static Analysis & Runtime Bug Hardening — fix InsiderTxSummary.source_url crash, dialect-agnostic upsert_insider_transaction, async session isolation di /portfolio/prices/refresh, OpenBB Fact schema, volume None guard; ruff 0 errors & mypy 0 errors pada 104 source files
- [x] PX-08: HARD-01 Decision Engine Gate — integrasi FAIL_LIQUIDITY (>25% ADV / NOT_EXECUTABLE_AT_ASSUMED_SIZE) & kecukupan kas 1 lot minimum ke run_decision_engine() dan check_trade_feasibility()
- [x] PX-09: ANL-06 Pass 3 Deterministic Claim Verifier — verify_ai_claims() di app/ai/adapter.py mendeteksi angka halusinasi di luar EvidenceBundle & frasa terlarang → auto-downgrade ke NEEDS_REVIEW
- [x] PX-10: MULTI-01 & MULTI-02 Multibagger Upgrade — 4 pipeline riset (QUALITY_COMPOUNDER, EARNINGS_INFLECTION, TURNAROUND, UNDERAPPRECIATED_CATALYST) + ReverseMultibaggerScenario (syarat CAGR EPS 2x/3x/5x/10x dengan stres dilusi)
- [x] PX-11: HARD-05 Decision Attribution Engine — app/analytics/attribution.py + GET /api/v1/portfolio/attribution (dekomposisi benchmark, sektor, stock-specific alpha, dividen, cost drag); total 403 unit & integration tests PASS

## Halaman Frontend

| Halaman | Route | Status |
|---------|-------|--------|
| Overview / Dashboard | `/` | ✅ |
| Stock Explorer | `/explorer` | ✅ |
| Screener | `/screener` | ✅ |
| Decision Center | `/decisions` | ✅ |
| My Portfolio | `/portfolio` | ✅ |
| Import Transaksi | `/portfolio/import` | ✅ |
| Broker Connections | `/portfolio/broker` | ✅ |
| Portfolio Health | `/portfolio/health` | ✅ |
| Position Intelligence | `/portfolio/positions` | ✅ |
| Loss Analyzer | `/portfolio/loss` | ✅ |
| Rebalance Simulator | `/portfolio/rebalance` | ✅ |
| Daily Intelligence | `/daily` | ✅ |
| Macro & Policy | `/macro` | ✅ |
| Research Notebook | `/notebook` | ✅ |
| Decision Journal | `/journal` | ✅ |
| Performance Lab | `/performance` | ✅ |
| Data & Settings | `/settings` | ✅ |
