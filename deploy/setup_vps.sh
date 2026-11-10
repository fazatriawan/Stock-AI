#!/usr/bin/env bash
# setup_vps.sh — Setup awal VPS Ubuntu 22.04 untuk Stock Intelligence API
# Jalankan sekali sebagai root atau user dengan sudo.
# TIDAK dieksekusi otomatis — jalankan manual via SSH.

set -euo pipefail

echo "=== Stock Intelligence VPS Setup ==="
echo "Target: Ubuntu 22.04, Python 3.12, PostgreSQL 16, PM2, Nginx"

# ---------------------------------------------------------------------------
# 1. Update sistem
# ---------------------------------------------------------------------------
apt-get update && apt-get upgrade -y

# ---------------------------------------------------------------------------
# 2. Install dependensi sistem
# ---------------------------------------------------------------------------
apt-get install -y \
    python3.12 python3.12-venv python3.12-dev \
    postgresql postgresql-contrib \
    nginx \
    curl git build-essential \
    libpq-dev libssl-dev \
    unzip jq htop

# ---------------------------------------------------------------------------
# 3. Node.js 20 (untuk PM2)
# ---------------------------------------------------------------------------
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs
npm install -g pm2

# ---------------------------------------------------------------------------
# 4. PostgreSQL — buat user & database
# ---------------------------------------------------------------------------
echo ">> Setup PostgreSQL..."
sudo -u postgres psql <<'PSQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'stock_user') THEN
    CREATE USER stock_user WITH PASSWORD 'CHANGE_THIS_PASSWORD';
  END IF;
END$$;

CREATE DATABASE stock_intelligence OWNER stock_user;
GRANT ALL PRIVILEGES ON DATABASE stock_intelligence TO stock_user;
PSQL

# Aktifkan autentikasi password lokal
PG_HBA="/etc/postgresql/16/main/pg_hba.conf"
if [ -f "$PG_HBA" ]; then
    sed -i 's/local   all             all                                     peer/local   all             all                                     md5/' "$PG_HBA"
    systemctl restart postgresql
fi

# ---------------------------------------------------------------------------
# 5. Buat direktori aplikasi
# ---------------------------------------------------------------------------
APP_DIR="/opt/stock-intelligence"
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/backups"
mkdir -p "$APP_DIR/logs"

# ---------------------------------------------------------------------------
# 6. Python virtual environment
# ---------------------------------------------------------------------------
echo ">> Setup Python venv..."
python3.12 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip

# ---------------------------------------------------------------------------
# 7. Nginx reverse proxy
# ---------------------------------------------------------------------------
echo ">> Setup Nginx..."
cp /tmp/stock-nginx.conf /etc/nginx/sites-available/stock-intelligence 2>/dev/null || true
ln -sf /etc/nginx/sites-available/stock-intelligence /etc/nginx/sites-enabled/ 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
nginx -t && systemctl reload nginx

# ---------------------------------------------------------------------------
# 8. PM2 startup
# ---------------------------------------------------------------------------
pm2 startup systemd -u root --hp /root 2>/dev/null || true

echo ""
echo "=== Setup selesai! ==="
echo "Langkah selanjutnya:"
echo "  1. Upload kode: scp -r services/api user@VPS:/opt/stock-intelligence/"
echo "  2. Copy .env:  scp services/api/.env user@VPS:/opt/stock-intelligence/api/.env"
echo "  3. Install deps: /opt/stock-intelligence/venv/bin/pip install -r /opt/stock-intelligence/api/requirements.txt"
echo "  4. Jalankan migrasi: cd /opt/stock-intelligence/api && alembic upgrade head"
echo "  5. Start PM2: pm2 start /opt/stock-intelligence/ecosystem.config.js"
echo "  6. Save PM2: pm2 save"
