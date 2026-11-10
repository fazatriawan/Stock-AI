# Panduan Deploy ke VPS

Panduan lengkap untuk memindahkan Stock Intelligence API dari laptop ke VPS (163.245.208.211).

---

## Deploy Cepat (setelah setup awal)

Setelah setup selesai, deploy cukup **satu perintah**:

```bash
bash deploy/deploy.sh
```

Deploy + migrasi database dari laptop:
```bash
bash deploy/deploy.sh --with-db
```

Deploy + bootstrap 200+ saham IDX:
```bash
bash deploy/deploy.sh --bootstrap
```

---

## Prasyarat

- VPS Ubuntu 22.04 dengan SSH akses (password dibutuhkan hanya di Langkah 0)
- Python 3.12+ di VPS (diinstall oleh `setup_vps.sh`)
- Koneksi internet di VPS untuk yfinance / Sectors API

---

## Langkah 0 — Setup SSH Key (sekali saja, butuh password terakhir kali)

Jalankan dari laptop:

```bash
bash deploy/setup_ssh_key.sh
```

Script ini akan:
1. Membuat SSH key `~/.ssh/stock_intelligence_vps` (jika belum ada)
2. Menyalin public key ke VPS — **password VPS dibutuhkan sekali ini saja**
3. Menambah alias `stock-vps` ke `~/.ssh/config`

Setelah selesai, semua `ssh`/`scp` ke VPS tidak perlu password lagi.

---

## Langkah 1 — Setup Awal VPS (sekali saja)

SSH ke VPS, lalu jalankan setup script:

```bash
ssh root@163.245.208.211

# Upload setup script
# (dari laptop):
scp deploy/setup_vps.sh root@163.245.208.211:/tmp/

# Di VPS:
bash /tmp/setup_vps.sh
```

Script ini akan menginstall:
- Python 3.12, Node.js 20, PostgreSQL 16
- PM2 (process manager)
- Nginx (reverse proxy)

---

## Langkah 2 — Deploy dengan Satu Perintah

Setelah SSH key terpasang (Langkah 0) dan VPS sudah di-setup (Langkah 1), cukup jalankan:

```bash
# Dari root project (stock-intelligence/)
bash deploy/deploy.sh
```

Script `deploy.sh` secara otomatis:
1. Cek SSH key (tidak perlu password)
2. Upload kode API via rsync (cepat, hanya file yang berubah)
3. Buat `.env` di VPS otomatis — password DB digenerate acak, API key dikopi dari laptop
4. Install Python dependencies
5. Jalankan `alembic upgrade head`
6. Restart PM2

> **Catatan `.env`**: Jika `.env` sudah ada di VPS, script tidak menimpanya. Edit manual di VPS:
> ```bash
> ssh stock-vps "nano /opt/stock-intelligence/api/.env"
> ssh stock-vps "pm2 restart stock-api"
> ```

---

## Langkah 3 — Setup Nginx (sekali saja)

```bash
# Upload nginx config (dari laptop)
scp deploy/nginx.conf stock-vps:/etc/nginx/sites-available/stock-intelligence

# Di VPS
ssh stock-vps "ln -sf /etc/nginx/sites-available/stock-intelligence /etc/nginx/sites-enabled/ && rm -f /etc/nginx/sites-enabled/default && nginx -t && systemctl reload nginx"
```

---

## Langkah 4 — Migrasi Database (opsional)

Jika ingin memindahkan data dari laptop ke VPS:

```bash
bash deploy/deploy.sh --with-db
```

Atau manual:
```bash
bash deploy/migrate_db.sh 163.245.208.211 root
```

---

## Langkah 5 — Bootstrap IDX Full (opsional, butuh waktu ~30 menit)

Jalankan saat deploy:
```bash
bash deploy/deploy.sh --bootstrap
```

Atau manual setelah deploy:
```bash
ssh stock-vps "curl -X POST http://localhost:8000/admin/bootstrap/idx"
```

---

## Verifikasi

```bash
# Cek API hidup
curl http://163.245.208.211:8000/health

# Cek PM2
ssh stock-vps "pm2 status"

# Cek logs
ssh stock-vps "pm2 logs stock-api --lines 20"
```

---

## Update Kode (setelah setup awal)

Cukup:
```bash
bash deploy/deploy.sh
```

Script menggunakan `rsync`, hanya upload file yang berubah (cepat).

---

## Troubleshooting

### API tidak bisa connect ke PostgreSQL
```bash
ssh stock-vps "systemctl status postgresql"
ssh stock-vps "sudo -u postgres psql -c '\l'"
```

### PM2 crash loop
```bash
ssh stock-vps "pm2 logs stock-api --lines 100"
```

### yfinance rate limited
```bash
ssh stock-vps "sed -i 's/IDX_BOOTSTRAP_DAYS=1825/IDX_BOOTSTRAP_DAYS=365/' /opt/stock-intelligence/api/.env"
ssh stock-vps "pm2 restart stock-api"
```

### Reset .env di VPS
```bash
# Hapus .env di VPS, lalu deploy ulang — script akan generate ulang
ssh stock-vps "rm /opt/stock-intelligence/api/.env"
bash deploy/deploy.sh
```

---

## Arsitektur di VPS

```
Internet
  │
  ▼
Nginx :80 (/api/ → proxy)
  │
  ▼
PM2 → Uvicorn :8000 (FastAPI)
  │
  ▼
PostgreSQL :5432 (lokal VPS)
```

Scheduler APScheduler berjalan dalam proses Uvicorn yang sama:
- **setiap 5 menit**: polling harga terkini (jam bursa)
- **02:00 WIB**: backup database
- **setiap 15 menit**: health probe provider
- **Minggu 08:00 WIB**: refresh fundamental IDX
- **Senin 06:00 WIB**: cek bootstrap IDX (jika < 50 instrumen)
