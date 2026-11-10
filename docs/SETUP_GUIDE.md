# Setup Guide — Stock Intelligence (R7 First Usable Release)

**Tujuan:** Menjalankan app dengan data pasar nyata (bukan mock) untuk pertama kali.  
**Estimasi waktu:** 15–30 menit.  
**Prasyarat:** Docker Desktop aktif, Python 3.12+, Node 20+.

---

## Daftar Isi

1. [Kloning & struktur](#1-kloning--struktur)
2. [Environment variables](#2-environment-variables)
3. [Jalankan database & Redis](#3-jalankan-database--redis)
4. [Migrasi database](#4-migrasi-database)
5. [Seed data live (yfinance)](#5-seed-data-live-yfinance)
6. [Verifikasi data nyata](#6-verifikasi-data-nyata)
7. [Jalankan frontend](#7-jalankan-frontend)
8. [Konfigurasi opsional](#8-konfigurasi-opsional)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Kloning & struktur

```
stock-intelligence/
  services/api/     → FastAPI backend (Python)
  apps/web/         → Next.js frontend (TypeScript)
  scripts/          → backup.sh, restore.sh
  docs/             → dokumentasi arsitektur
```

Pasang dependensi backend:

```bash
cd services/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Environment variables

```bash
cd services/api
cp .env.example .env
```

Edit `.env` — minimal yang **wajib** diisi:

```bash
# Wajib diganti (string acak min 32 karakter):
SECRET_KEY=isi-dengan-string-acak-panjang-di-sini

# Sudah diisi benar di .env.example — cukup periksa:
DATABASE_URL=postgresql+asyncpg://stock_user:change_me_password@localhost:5432/stock_intelligence
DATABASE_URL_SYNC=postgresql://stock_user:change_me_password@localhost:5432/stock_intelligence
YFINANCE_ENABLED=true

# Opsional tapi sangat dianjurkan (untuk fitur analisis AI):
ANTHROPIC_API_KEY=sk-ant-...
```

> **Jangan commit `.env`** — sudah ada di `.gitignore`.

### Enkripsi backup (sangat dianjurkan)

```bash
# Generate passphrase kuat:
openssl rand -base64 32
# Paste hasilnya ke:
BACKUP_ENCRYPTION_KEY=<hasil-di-atas>
```

---

## 3. Jalankan database & Redis

```bash
# Dari root repo:
docker compose up db redis -d

# Tunggu hingga healthy (~10 detik):
docker compose ps
# STATUS harus: healthy
```

Jika port 5432 sudah dipakai PostgreSQL lokal:

```bash
# Edit docker-compose.yml, ubah ports db:
ports:
  - "5433:5432"
# Dan sesuaikan DATABASE_URL di .env:
DATABASE_URL=postgresql+asyncpg://stock_user:change_me_password@localhost:5433/stock_intelligence
DATABASE_URL_SYNC=postgresql://stock_user:change_me_password@localhost:5433/stock_intelligence
```

---

## 4. Migrasi database

Jalankan **satu kali** untuk membuat semua tabel (26 tabel + 3 migration step):

```bash
cd services/api
source .venv/bin/activate
alembic upgrade head
```

Output yang diharapkan:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 000_initial_schema ...
INFO  [alembic.runtime.migration] Running upgrade 000_initial_schema -> 001_add_trade_journal ...
INFO  [alembic.runtime.migration] Running upgrade 001_add_trade_journal -> 002_research_notes ...
INFO  [alembic.runtime.migration] Running upgrade 002_research_notes -> 003_investment_policies ...
```

Verifikasi:
```bash
# Harus tampil "Current revision(s) for...: 003_investment_policies"
alembic current
```

---

## 5. Seed data live (yfinance)

### 5a. Jalankan API server

```bash
cd services/api
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Buka [http://localhost:8000/docs](http://localhost:8000/docs) untuk Swagger UI.

### 5b. Seed instrument catalog

```bash
curl -s -X POST "http://localhost:8000/api/v1/admin/bootstrap?use_mock=false" | python3 -m json.tool
```

Respons sukses:
```json
{
  "message": "Bootstrap dimulai",
  "instruments_loaded": 20,
  "ohlcv_job": "running in background",
  "data_source": "live_provider"
}
```

> OHLCV berjalan di **background** — tunggu ~2–3 menit untuk 20 instrumen × 365 hari.  
> yfinance punya rate limit ~100 req/menit; bootstrap di-throttle otomatis.

### 5c. Pantau progress

```bash
# Cek berapa bar sudah masuk:
curl -s "http://localhost:8000/api/v1/stocks/IDX:BBCA/prices?days=5" | python3 -m json.tool
```

Jika `bars` sudah terisi → seed berhasil.

---

## 6. Verifikasi data nyata

Jalankan **semua** perintah ini satu per satu untuk memastikan stack bekerja end-to-end:

### Harga live

```bash
# Harga terkini BBCA (IDX)
curl -s "http://localhost:8000/api/v1/stocks/IDX:BBCA/overview" | python3 -m json.tool | grep -A3 '"last_price"'
# Harus muncul angka nyata (bukan mock sintetis ~9500)

# Harga AAPL (US)
curl -s "http://localhost:8000/api/v1/stocks/US:AAPL/overview" | python3 -m json.tool | grep '"last_price"'
```

### Analisis deterministik

```bash
curl -s "http://localhost:8000/api/v1/stocks/IDX:BBCA/analysis" | python3 -m json.tool | grep -E '"action"|"composite_score"'
# action: BUY / HOLD / WAIT / INSUFFICIENT_DATA (bergantung kondisi pasar hari ini)
```

### Integrity check

```bash
curl -s "http://localhost:8000/api/v1/stocks/IDX:BBCA/integrity" | python3 -m json.tool | grep '"status"'
# "status": "CLEAN" atau "CONFLICT" jika ada anomali data
```

### Ops status

```bash
curl -s "http://localhost:8000/api/v1/admin/ops" | python3 -m json.tool | grep -A3 '"providers"'
# yfinance status: "OK"
```

### Provider health

```bash
curl -s "http://localhost:8000/api/v1/data/health" | python3 -m json.tool
# yfinance: { "status": "OK" }
# mock: { "status": "OK" } (selalu ada sebagai fallback)
```

---

## 7. Jalankan frontend

```bash
cd apps/web
npm install
npm run dev
```

Buka [http://localhost:3000](http://localhost:3000).

Halaman yang langsung bisa dicoba dengan data nyata:
- `/explorer` → cari saham, lihat harga + teknikal
- `/decisions` → rekomendasi BUY/HOLD/SELL/WAIT
- `/daily` → briefing harian, status IDX & NYSE
- `/settings` → edit Investment Policy Statement (IPS)

---

## 8. Konfigurasi opsional

### Aktifkan analisis AI (Claude)

```bash
# Di .env:
ANTHROPIC_API_KEY=sk-ant-...
```

Setelah restart API, `GET /stocks/{symbol}/analysis` akan menyertakan:
- `ai_enriched: true`
- `ai_macro_context`: konteks makro dari Claude
- `ai_identified_risks`: risiko tambahan
- Critic pass: kelemahan thesis bull

### Aktifkan Sectors.app (data fundamental IDX premium)

Daftar di [sectors.app/api](https://sectors.app) untuk mendapatkan API key Insider tier ($59/bulan).

```bash
# Di .env:
SECTORS_API_KEY=your_key_here
SECTORS_ENABLED=true
```

Setelah restart, `POST /stocks/IDX:BBCA/fundamentals/refresh` akan mengambil data fundamental dari Sectors (lebih akurat dari yfinance untuk IDX).

### Setup backup otomatis

Backup berjalan otomatis tiap hari 02:00 WIB via APScheduler (sudah aktif bersama API server).

Untuk juga punya backup dari luar proses (lebih aman):

```bash
# Crontab: backup jam 02:30 WIB setiap hari
crontab -e
# Tambahkan baris:
30 2 * * * cd /path/to/stock-intelligence && bash scripts/backup.sh >> /var/log/stock_backup.log 2>&1
```

Verifikasi sentinel backup:

```bash
# Setelah backup pertama berjalan:
curl -s "http://localhost:8000/api/v1/admin/ops" | python3 -m json.tool | grep -A4 '"backup"'
# "status": "OK", "age_hours": < 24
```

---

## 9. Troubleshooting

### `alembic upgrade head` gagal: "no such table"

```bash
# Pastikan DATABASE_URL_SYNC diisi dengan format postgresql:// (bukan asyncpg)
echo $DATABASE_URL_SYNC
# Harus: postgresql://stock_user:...
```

### Bootstrap timeout / data tidak masuk

yfinance kadang rate-limit atau return data kosong. Coba per-saham:

```bash
# Refresh harga satu saham:
curl -X POST "http://localhost:8000/api/v1/stocks/IDX:BBCA/prices/refresh"
# Refresh fundamental:
curl -X POST "http://localhost:8000/api/v1/stocks/IDX:BBCA/fundamentals/refresh"
```

### Data masih tampil mock (harga ~9500 untuk BBCA)

Cek apakah bootstrap live sudah berjalan:

```bash
curl -s "http://localhost:8000/api/v1/stocks/IDX:BBCA/prices?days=3" | python3 -m json.tool | grep '"provider"'
# "provider": "yfinance"  ← live
# "provider": "mock"      ← masih mock, bootstrap belum selesai
```

Jika masih mock, trigger ulang:
```bash
curl -X POST "http://localhost:8000/api/v1/admin/bootstrap?use_mock=false"
```

### Koneksi DB gagal

```bash
# Cek container running:
docker compose ps

# Cek log DB:
docker compose logs db --tail=20

# Test koneksi langsung:
psql postgresql://stock_user:change_me_password@localhost:5432/stock_intelligence -c "SELECT 1"
```

### Port 3000 / 8000 sudah dipakai

```bash
# Jalankan di port lain:
uvicorn app.main:app --reload --port 8001
# Dan update ALLOWED_ORIGINS di .env:
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
```

---

## Checklist R7

Centang tiap item sebelum mulai pakai untuk riset nyata:

- [ ] `alembic current` menampilkan `003_investment_policies`
- [ ] `GET /api/v1/admin/ops` → yfinance status: `OK`
- [ ] `GET /api/v1/stocks/IDX:BBCA/prices?days=5` → bars tidak kosong, provider: `yfinance`
- [ ] `GET /api/v1/stocks/IDX:BBCA/analysis` → action bukan `INSUFFICIENT_DATA`
- [ ] `GET /api/v1/daily` → `market_sessions` muncul IDX + NYSE
- [ ] `GET /api/v1/settings/policy` → mengembalikan IPS default
- [ ] Frontend [localhost:3000](http://localhost:3000) → bisa buka `/decisions`
- [ ] `.env` tidak ter-commit ke git: `git status` tidak menampilkan `.env`

---

## Mode offline (tanpa internet / testing)

Jika tidak ada koneksi internet atau hanya ingin testing:

```bash
# Gunakan data sintetis:
curl -X POST "http://localhost:8000/api/v1/admin/bootstrap-mock"
```

Data mock deterministik — angka konsisten antar restart, tapi **bukan data pasar nyata**.
Jangan gunakan data mock untuk keputusan investasi.
