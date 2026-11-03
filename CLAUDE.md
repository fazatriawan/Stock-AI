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
