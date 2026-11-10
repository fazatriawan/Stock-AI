# Backup & Restore — Stock Intelligence

**Berlaku untuk:** PostgreSQL production. SQLite development tidak membutuhkan prosedur ini.

---

## Prasyarat

```bash
# PostgreSQL client tools (pg_dump, psql)
brew install postgresql  # macOS
apt-get install postgresql-client  # Debian/Ubuntu
```

---

## Variabel Environment

Semua variabel bisa diset di `services/api/.env` atau di environment shell:

| Variabel | Wajib | Default | Keterangan |
|---|---|---|---|
| `DATABASE_URL_SYNC` | Ya | — | `postgres://user:pass@host:port/dbname` |
| `BACKUP_DIR` | Tidak | `./backups/` | Direktori output backup |
| `BACKUP_RETENTION_DAYS` | Tidak | `30` | Hapus backup lebih dari N hari |
| `BACKUP_ENCRYPTION_KEY` | **Sangat disarankan** | — | Passphrase AES-256-CBC; kosong = simpan plain |

**Penting:** Set `BACKUP_ENCRYPTION_KEY` di production. File plain `.sql.gz` berisi seluruh data tanpa enkripsi.

---

## Cara Backup Manual

```bash
cd stock-intelligence

# Backup dengan enkripsi
export BACKUP_ENCRYPTION_KEY="passphrase-rahasia-yang-kuat"
./scripts/backup.sh
```

Output di `./backups/`:
```
backups/
  stock_intel_20261104_120000.sql.gz.enc   ← dump terenkripsi
  stock_intel_20261104_120000.sha256       ← checksum SHA256
```

Jika `BACKUP_ENCRYPTION_KEY` tidak diset, output berupa `.sql.gz` (plain — **jangan di-commit**).

---

## Cara Restore

```bash
# Restore ke database yang sama (dari env)
export BACKUP_ENCRYPTION_KEY="passphrase-rahasia-yang-kuat"
./scripts/restore.sh backups/stock_intel_20261104_120000.sql.gz.enc

# Restore ke database lain (untuk testing)
./scripts/restore.sh backups/stock_intel_20261104_120000.sql.gz.enc \
    postgres://user:pass@localhost:5432/stock_intel_staging
```

Script akan:
1. Meminta konfirmasi (`yes`) sebelum menimpa data
2. Verifikasi checksum SHA256
3. Dekripsi dengan `BACKUP_ENCRYPTION_KEY`
4. Jalankan `psql` restore dengan `ON_ERROR_STOP=1`

---

## Jadwal Otomatis — Cron

Tambahkan ke crontab (`crontab -e`) untuk backup otomatis setiap hari jam 02:00:

```cron
0 2 * * * cd /path/ke/stock-intelligence && BACKUP_ENCRYPTION_KEY="passphrase-kamu" ./scripts/backup.sh >> /var/log/stock_intel_backup.log 2>&1
```

Atau pakai `systemd` timer — lihat contoh di bawah.

### systemd timer (Linux)

`/etc/systemd/system/stock-intel-backup.service`:
```ini
[Unit]
Description=Stock Intelligence Database Backup

[Service]
Type=oneshot
WorkingDirectory=/path/ke/stock-intelligence
Environment="BACKUP_ENCRYPTION_KEY=passphrase-kamu"
ExecStart=/path/ke/stock-intelligence/scripts/backup.sh
StandardOutput=journal
StandardError=journal
```

`/etc/systemd/system/stock-intel-backup.timer`:
```ini
[Unit]
Description=Daily Stock Intelligence Backup

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now stock-intel-backup.timer
systemctl list-timers stock-intel-backup.timer
```

---

## Verifikasi Restore (Checklist)

Setelah restore ke DB uji coba:

```bash
# 1. Pastikan tabel ada
psql "$TARGET_URL" -c "\dt" | grep -E "(instruments|portfolios|investment_policies)"

# 2. Hitung row
psql "$TARGET_URL" -c "SELECT COUNT(*) FROM instruments;"
psql "$TARGET_URL" -c "SELECT COUNT(*) FROM trades;"

# 3. Jalankan migration (kalau restore ke versi lebih baru)
DATABASE_URL_SYNC="$TARGET_URL" alembic upgrade head

# 4. Jalankan API test
cd services/api && pytest tests/ -v --tb=short
```

---

## Catatan Keamanan

- Path backup **tidak dicetak** ke stdout/log untuk mencegah bocornya lokasi file sensitif
- `PGPASSWORD` di-`unset` segera setelah koneksi database
- File temp dekripsi dihapus setelah restore selesai
- Backup `.sql.gz.enc` aman disimpan di cloud storage (S3, GCS, Backblaze B2)
- Jangan simpan `BACKUP_ENCRYPTION_KEY` di `.env` yang di-commit ke git
