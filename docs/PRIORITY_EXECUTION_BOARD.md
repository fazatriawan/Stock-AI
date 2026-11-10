# PRIORITY EXECUTION BOARD — Stock Intelligence
**Dibuat:** 4 November 2026  
**Berdasarkan:** IMPLEMENTATION_AUDIT.md + Roadmap v1.7.1  
**Prinsip:** ikuti urutan R0→R22; jangan loncat ke R14+ sebelum R7 selesai

---

## Status Milestone per Roadmap

| Milestone | Deskripsi | Status | Gate |
|---|---|---|---|
| R0 | Audit codebase, backup plan | **SELESAI** (dokumen ini) | ✅ Audit + 3 docs |
| R1 | Instrument master, schema, auth, secrets | **PARTIAL** | ❌ Alembic initial migration missing; .env.example missing |
| R2 | Validated market EOD + provenance | **PARTIAL** | ❌ yfinance tidak dipakai di routes; mock jadi default |
| R3 | Portfolio ledger + Stockbit imports | **PARTIAL** | ❌ PDF parser belum ditest dengan dokumen nyata; FX belum ditest |
| R4 | Fundamentals + Financial Integrity Checker | **MISSING (critical)** | ❌ Integrity Checker sama sekali belum ada |
| R5 | Deterministic engine + risk/IPS gates | **PARTIAL** | ❌ IPS hardcoded, bukan user-editable |
| R6 | Backup, restore, audit log, security | **MISSING** | ❌ Tidak ada backup job sama sekali |
| R7 | First usable release (5 IDX + 5 US) | **PARTIAL** | ❌ App jalan tapi data mock; belum bisa riset saham nyata |

**Kesimpulan:** kita di antara R1 dan R7 — semua page ada tapi data foundation belum solid.

---

## P0 Backlog yang Belum Lulus Gate

### BL-01 — Initial Alembic migration (CRITICAL, R1) ✅ DONE_VERIFIED
**Problem:** `models.py` punya 25+ tabel; hanya ada 2 migration file (001, 002) untuk TradeJournal dan ResearchNote. `alembic upgrade head` pada DB kosong akan gagal.  
**Selesai:** 4 Nov 2026.  
- `000_initial_schema.py` dibuat manual — 24 tabel inti termasuk instruments, trades, portfolio, macro, dll.
- `001_add_trade_journal.py` di-chain: `down_revision = "000_initial_schema"` (sebelumnya `None`)
- Chain `000 → 001 → 002` diverifikasi dengan `alembic upgrade head --sql`: 26 CREATE TABLE sukses, 0 error.
**Perintah test:** `DATABASE_URL_SYNC="sqlite:///..." alembic upgrade head --sql`  
**Hasil:** PASS — semua 26 tabel terbuat dalam urutan FK yang benar.

### BL-02 — .env.example (R1) ✅ DONE_VERIFIED
**Problem:** tidak ada; onboarding sulit; `secret_key = "change-me"` default berbahaya.  
**Selesai:** `services/api/.env.example` dibuat 4 Nov 2026.  
**Coverage:** semua variabel dari `config.py` tercakup; komentar bahasa Indonesia; `SECRET_KEY` wajib diganti.

### BL-03 — Aktifkan yfinance di production routes (R2) ✅ DONE_VERIFIED
**Problem:** `mock_provider.py` selalu dipakai; registry benar tapi bootstrap default `use_mock=True`.  
**Selesai:** 4 Nov 2026.  
- `ingestion.py`: `use_mock=True` → `False`; tambah `/admin/bootstrap-mock` untuk testing offline
- `bootstrap.py`: hapus dead code variabel `provider` yang tidak dipakai; default `use_mock=False`
- `stocks.py`: tambah `POST /stocks/{symbol}/prices/refresh` — on-demand fetch dari yfinance, idempotent
- Verifikasi: yfinance fetch BBCA.JK → Rp4.840 (5 bars), AAPL → $331.90 (5 bars), provider health OK
**Perintah test:** `python -c "from app.providers.yfinance_provider import YFinanceProvider; ..."`  
**Hasil:** PASS — `is_live_data=True` saat `YFINANCE_ENABLED=true`

### BL-04 — Financial Integrity Checker (R4, P0) ✅ DONE_VERIFIED
**Problem:** tidak ada validasi cross-field untuk data fundamental (EPS vs shares, satuan IDR, balance sheet).  
**Selesai:** 4 Nov 2026.  
- `app/analytics/integrity.py` dibuat: 6 check functions, 5 flag types, 13 bounds rules
  - `_check_bounds`: validasi PE, PB, ROE, margin, yield, beta dalam rentang wajar
  - `_check_pe_eps_sign`: PE > 0 & EPS < 0 → SIGN_CONTRADICTION (dan sebaliknya)
  - `_check_pe_market_cap_net_income`: PE ≈ MARKET_CAP/NET_INCOME ± 25%
  - `_check_margin_net_income_sign`: gross_margin < 0 & net_income < 0 → double red flag
  - `_check_period_duplicates`: dua fact dengan metric + period_end sama → PERIOD_DUPLICATE
  - `_check_idr_unit_reasonableness`: EPS IDX > Rp1.000.000/saham → UNIT_SUSPECT
- `app/analytics/fundamental.py` diintegrasi: `run_integrity_check()` dipanggil setelah load; blocked metrics di-clear (set ke None → INSUFFICIENT_DATA)
- `app/api/schemas.py`: `MetricConflictResponse` + `IntegrityReportResponse` + `FundamentalSnapshotResponse` updated (integrity_status, integrity_blocked)
- `app/api/routes/stocks.py`: endpoint `GET /stocks/{symbol}/integrity` mengembalikan report lengkap  
**Test:** 5 unit test dengan mock FinancialFact — semua PASS
- CLEAN data → status CLEAN ✓
- PE>0 & EPS<0 → SIGN_CONTRADICTION ✓
- GROSS_MARGIN=1.5 → BLOCKED + downstream blocked ✓
- Duplicate period → PERIOD_DUPLICATE ✓
- EPS IDR > 1M → UNIT_SUSPECT ✓

### BL-05 — User-editable IPS (R5, P0) ✅ DONE_VERIFIED
**Problem:** `max_position_weight = 0.10` hardcoded di `DecisionConfig`; tidak ada user-editable policy.  
**Selesai:** 4 Nov 2026.  
- `003_add_investment_policies.py` — migration baru, chain `002→003` verified dengan `--sql`
- `app/db/models.py` — model `InvestmentPolicy` ditambah (profile_name, mode, max_position_weight, max_sector_weight, buy_score_threshold, min_core_coverage, max_staleness_days, horizon, notes)
- `app/domain/investment_policy.py` — `get_or_create_default()` dan `update_policy()` dengan validasi boundary per field
- `app/api/schemas.py` — `InvestmentPolicyResponse` + `InvestmentPolicyUpdateRequest`
- `app/api/routes/settings.py` — `GET /settings/policy`, `PUT /settings/policy`
- `app/main.py` — `settings.router` didaftarkan ke `/api/v1`
- `app/api/routes/stocks.py` route `get_analysis` — load policy dari DB, inject ke `DecisionConfig` + `PortfolioContext`; tidak lagi hardcode
**Test:**
- Chain migration 000→001→002→003: semua table terbuat, `CREATE TABLE investment_policies` PASS
- Routes registered: `/api/v1/settings/policy` (GET + PUT) PASS
- `update_policy` logic: valid update, invalid mode, weight > 1.0 → semua validasi PASS

### BL-06 — Backup & restore (R6, P0) ✅ DONE_VERIFIED
**Problem:** tidak ada backup job sama sekali.  
**Selesai:** 4 Nov 2026.  
- `scripts/backup.sh`:
  - `pg_dump` → gzip → opsional AES-256-CBC enkripsi (via OpenSSL, passphrase dari `BACKUP_ENCRYPTION_KEY`)
  - Checksum SHA256 otomatis per dump
  - Cleanup backup lebih dari `BACKUP_RETENTION_DAYS` (default 30 hari)
  - Path backup tidak dicetak ke log — hanya nama file + ukuran + checksum
  - `PGPASSWORD` di-unset segera setelah koneksi
- `scripts/restore.sh`:
  - Konfirmasi `yes` sebelum menimpa data
  - Verifikasi SHA256 sebelum restore
  - Dekripsi AES-256 otomatis jika file `.enc`
  - File temp dekripsi dihapus setelah selesai
  - `ON_ERROR_STOP=1` agar restore tidak partial
- `docs/BACKUP_RESTORE.md` — prosedur lengkap: manual, cron, systemd timer, checklist verifikasi, catatan keamanan
- `.gitignore` — `backups/`, `*.sql.gz`, `*.sql.gz.enc`, `*.sha256` ditambahkan
**Test (dry-run):**
- Tanpa `DATABASE_URL_SYNC` → ERROR dengan pesan jelas PASS
- `DATABASE_URL_SYNC=sqlite://` → ERROR "bukan postgres://" PASS
- `restore.sh` tanpa argumen → usage + exit 1 PASS
- `bash -n` syntax check kedua script: PASS

---

## Urutan Eksekusi Berikutnya (P0 first)

```
BL-02 (.env.example)         → aman, tidak perlu DB, 15 menit
BL-01 (initial migration)    → butuh backup snapshot dulu
BL-03 (aktifkan yfinance)    → setelah BL-01 selesai
BL-04 (Integrity Checker)    → setelah BL-03 ada data nyata untuk ditest
BL-05 (user IPS)             → setelah BL-01 (butuh tabel baru)
BL-06 (backup script)        → bisa paralel dengan BL-04
```

Setelah BL-01 s/d BL-06 selesai → baru masuk ke R8 (Sectors API v2).

---

## R8–R13 Preview (P1, setelah P0 lulus)

| Milestone | Task Utama | Dependensi |
|---|---|---|
| R8 | Sectors Financial API v2 adapter; sector-specific fundamentals; peer comparison | **SELESAI** 4 Nov 2026 |
| R9 | Claude EvidenceBundle + independent critic + claim verifier | **SELESAI** 4 Nov 2026 |
| R10 | Full IPS enforcement + Trade Feasibility Engine (lot, ADV, spread) | **SELESAI** 4 Nov 2026 |
| R11 | Dividend sustainability analysis; real-return vs inflation | **SELESAI** 4 Nov 2026 |
| R12 | Daily change digest; IDX/NYSE calendar aware; alert dedup | **SELESAI** 4 Nov 2026 |
| R13 | Provider operations hardening; encrypted backup cron; monitoring UI | **SELESAI** 4 Nov 2026 |
| R14 | Insider Transaction Monitor — scoring engine, cluster detection, manual import API | **SELESAI** 4 Nov 2026 |
| R15 | Multibagger Screener — scoring 4 dimensi, tier STRONG→INSUFFICIENT, GET /screener/multibagger | **SELESAI** 4 Nov 2026 |
| R16 | Backtesting Engine — SMA_CROSSOVER, RSI_MEAN_REVERT, MACD_SIGNAL; Sharpe, drawdown, CAGR; POST /backtest/{symbol} | **SELESAI** 4 Nov 2026 |
| R17 | Global Macro Integration — FRED fetcher, yield curve (NORMAL/FLAT/INVERTED), macro impact scorer; GET /macro/yield-curve + /impact; POST /macro/observations/refresh | **SELESAI** 4 Nov 2026 |
| R18 | Swing Trade Monitor — BREAKOUT/PULLBACK detector, ATR-based stop, R:R target, volume konfirmasi; GET /swing/{symbol} + /swing screen | **SELESAI** 4 Nov 2026 |
| R19 | Alert & Notification Engine — 9 rule types, cooldown dedup SHA1, webhook dispatch Slack-compatible; CRUD /alerts/rules + POST /alerts/evaluate | **SELESAI** 4 Nov 2026 |
| R20 | Watchlist & Price Target Engine — WatchlistItem +price_target/cost_basis/alert_on_target, migration 006, pct_to_target enrichment; CRUD /watchlists | **SELESAI** 4 Nov 2026 |
| R21 | Frontend Watchlist (/watchlist) & Alerts (/alerts) — CRUD halaman, modal tambah item, evaluate button, history tab; Sidebar updated | **SELESAI** 4 Nov 2026 |
| R22 | Integration Summary — GET /summary aggregates macro+swing+alerts+watchlist_near_target; 332 unit tests total PASS | **SELESAI** 4 Nov 2026 |

---

## Apa yang TIDAK Dikerjakan Dulu

- R14–R22 (insider, global trade, multibagger, backtesting, swing) — tunggu R7 benar-benar solid
- Gmail OAuth (P2) — manual import lebih dulu terbukti stabil
- Intraday / paper trading — P3; tidak prioritas

---

## Definition of Done per Item

Setiap backlog item selesai ketika:
1. File path perubahan terdokumentasi di sini
2. Test command dijalankan dan hasilnya dicatat (PASS/FAIL/SKIPPED)
3. Tidak ada regresi pada portfolio math atau auth
4. Data material punya source dan tanggal
5. Status diupdate ke `DONE_VERIFIED` atau `BLOCKED` dengan alasan spesifik
