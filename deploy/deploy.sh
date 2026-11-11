#!/usr/bin/env bash
# deploy.sh — One-click deploy Stock Intelligence API ke VPS
# Prasyarat: sudah jalankan deploy/setup_ssh_key.sh (SSH key harus terpasang)
#
# Penggunaan:
#   bash deploy/deploy.sh              # deploy normal
#   bash deploy/deploy.sh --with-db    # deploy + migrasi database dari laptop
#   bash deploy/deploy.sh --bootstrap  # deploy + trigger IDX bootstrap (30 menit)

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
VPS="stock-vps"                             # alias dari ~/.ssh/config
VPS_IP="163.245.208.211"
APP_DIR="/opt/stock-intelligence"
API_DIR="$APP_DIR/api"
VENV="$APP_DIR/venv/bin"
LOCAL_API="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/services/api"
LOCAL_DEPLOY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WITH_DB=false
WITH_BOOTSTRAP=false

for arg in "$@"; do
    case "$arg" in
        --with-db)       WITH_DB=true ;;
        --bootstrap)     WITH_BOOTSTRAP=true ;;
    esac
done

# ---------------------------------------------------------------------------
# Cek SSH key
# ---------------------------------------------------------------------------
echo "=== Stock Intelligence Deploy ==="
echo "Target: $VPS ($VPS_IP)"
echo ""

if ! ssh -o BatchMode=yes "$VPS" "true" 2>/dev/null; then
    echo "ERROR: Tidak bisa connect ke VPS tanpa password."
    echo "Jalankan setup SSH key dulu:"
    echo "  bash deploy/setup_ssh_key.sh"
    exit 1
fi
echo ">> SSH OK"

# ---------------------------------------------------------------------------
# 1. Buat direktori di VPS
# ---------------------------------------------------------------------------
echo ""
echo ">> Buat direktori di VPS..."
ssh "$VPS" "mkdir -p $API_DIR $APP_DIR/backups $APP_DIR/logs"

# ---------------------------------------------------------------------------
# 2. Upload kode API
# ---------------------------------------------------------------------------
echo ">> Upload kode API..."
rsync -az --delete \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude 'venv' \
    --exclude '.venv' \
    --exclude '.pytest_cache' \
    --exclude '.mypy_cache' \
    --exclude '.ruff_cache' \
    --exclude 'htmlcov' \
    --exclude '*.egg-info' \
    "$LOCAL_API/" \
    "$VPS:$API_DIR/"
echo "   Kode API ter-upload"

# ---------------------------------------------------------------------------
# 3. Upload ecosystem.config.js
# ---------------------------------------------------------------------------
echo ">> Upload ecosystem.config.js..."
scp "$LOCAL_DEPLOY/ecosystem.config.js" "$VPS:$APP_DIR/"

# ---------------------------------------------------------------------------
# 3. Sync .env — hanya jika .env belum ada di VPS, generate dari template
# ---------------------------------------------------------------------------
echo ">> Cek .env di VPS..."
ENV_EXISTS=$(ssh "$VPS" "test -f $API_DIR/.env && echo yes || echo no")

if [ "$ENV_EXISTS" = "no" ]; then
    echo ">> .env belum ada di VPS, membuat dari laptop..."
    # Copy .env dari laptop, ganti DATABASE_URL ke localhost VPS
    DB_PASS=$(openssl rand -hex 16)
    SECRET_KEY=$(openssl rand -hex 32)

    # Ambil API keys dari .env laptop (jika ada)
    ANTHROPIC_KEY=""
    SECTORS_KEY=""
    if [ -f "$LOCAL_API/.env" ]; then
        ANTHROPIC_KEY=$(grep '^ANTHROPIC_API_KEY=' "$LOCAL_API/.env" 2>/dev/null | cut -d= -f2- || echo "")
        SECTORS_KEY=$(grep '^SECTORS_API_KEY=' "$LOCAL_API/.env" 2>/dev/null | cut -d= -f2- || echo "")
    fi

    # Boolean: harus "true" atau "false", tidak boleh kosong
    SECTORS_ENABLED_VAL="false"
    [ -n "$SECTORS_KEY" ] && SECTORS_ENABLED_VAL="true"

    ssh "$VPS" "mkdir -p $API_DIR && cat > $API_DIR/.env" <<EOF
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO
SECRET_KEY=$SECRET_KEY

DATABASE_URL=postgresql+asyncpg://stock_user:${DB_PASS}@localhost:5432/stock_intelligence
DATABASE_URL_SYNC=postgresql://stock_user:${DB_PASS}@localhost:5432/stock_intelligence
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

ANTHROPIC_MODEL=claude-sonnet-5-5
ANTHROPIC_API_KEY=${ANTHROPIC_KEY}

YFINANCE_ENABLED=true
SECTORS_ENABLED=${SECTORS_ENABLED_VAL}
SECTORS_API_KEY=${SECTORS_KEY}

OPENBB_ENABLED=false
INTRADAY_POLLING_ENABLED=true
IDX_BOOTSTRAP_DAYS=1825

ALLOWED_ORIGINS=http://${VPS_IP}:3000,http://localhost:3000
EOF

    # Update password PostgreSQL di VPS
    ssh "$VPS" "sudo -u postgres psql -c \"ALTER USER stock_user WITH PASSWORD '${DB_PASS}';\" 2>/dev/null || true"
    echo "   .env dibuat dengan password acak"
else
    echo "   .env sudah ada (skip)"
fi

# ---------------------------------------------------------------------------
# 4. Pastikan Python & venv tersedia
# ---------------------------------------------------------------------------
echo ""
echo ">> Cek Python venv..."
VENV_OK=$(ssh "$VPS" "test -f $VENV/pip && echo yes || echo no")
if [ "$VENV_OK" = "no" ]; then
    echo "   Venv belum ada, install Python + buat venv..."
    ssh "$VPS" "
        apt-get update -qq &&
        apt-get install -y -qq python3.12 python3.12-venv python3.12-dev libpq-dev build-essential &&
        python3.12 -m venv $APP_DIR/venv
    "
    echo "   Venv dibuat"
fi

# ---------------------------------------------------------------------------
# 5. Install Python dependencies
# ---------------------------------------------------------------------------
echo ">> Install Python dependencies..."
ssh "$VPS" "$VENV/pip install --quiet -r $API_DIR/requirements.txt"
echo "   Dependencies ter-install"

# ---------------------------------------------------------------------------
# 6. Migrasi database (opsional)
# ---------------------------------------------------------------------------
if [ "$WITH_DB" = "true" ]; then
    echo ""
    echo ">> Migrasi database dari laptop ke VPS..."
    bash "$LOCAL_DEPLOY/migrate_db.sh" "$VPS_IP" "root"
fi

# ---------------------------------------------------------------------------
# 7. Pastikan PostgreSQL & database tersedia
# ---------------------------------------------------------------------------
echo ""
echo ">> Cek PostgreSQL..."
PG_OK=$(ssh "$VPS" "systemctl is-active postgresql 2>/dev/null || echo inactive")
if [ "$PG_OK" != "active" ]; then
    echo "   Install PostgreSQL..."
    ssh "$VPS" "
        apt-get install -y -qq postgresql postgresql-contrib &&
        systemctl enable postgresql &&
        systemctl start postgresql
    "
fi

# Buat user & database jika belum ada
# Ekstrak password dari DATABASE_URL_SYNC: postgresql://user:PASSWORD@host:port/db
DB_PASS=$(ssh "$VPS" "grep '^DATABASE_URL_SYNC=' $API_DIR/.env | sed 's|.*://[^:]*:\([^@]*\)@.*|\1|'")
ssh "$VPS" "sudo -u postgres psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='stock_user'\" | grep -q 1 \
    && sudo -u postgres psql -c \"ALTER USER stock_user WITH PASSWORD '$DB_PASS';\" \
    || sudo -u postgres psql -c \"CREATE USER stock_user WITH PASSWORD '$DB_PASS';\"" 2>/dev/null || true
ssh "$VPS" "sudo -u postgres psql -tc \"SELECT 1 FROM pg_database WHERE datname='stock_intelligence'\" | grep -q 1 || sudo -u postgres psql -c \"CREATE DATABASE stock_intelligence OWNER stock_user; GRANT ALL PRIVILEGES ON DATABASE stock_intelligence TO stock_user;\"" 2>/dev/null || true
echo "   PostgreSQL OK"

# ---------------------------------------------------------------------------
# 8. Alembic upgrade
# ---------------------------------------------------------------------------
echo ""
echo ">> Alembic upgrade head..."
ssh "$VPS" "cd $API_DIR && $VENV/alembic upgrade head 2>&1 | tail -5"
echo "   Migrasi selesai"

# ---------------------------------------------------------------------------
# 8. Pastikan PM2 tersedia
# ---------------------------------------------------------------------------
echo ""
echo ">> Cek PM2..."
PM2_OK=$(ssh "$VPS" "which pm2 2>/dev/null && echo yes || echo no")
if [ "$PM2_OK" = "no" ]; then
    echo "   PM2 belum ada, install Node.js + PM2..."
    ssh "$VPS" "
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - &&
        apt-get install -y -qq nodejs &&
        npm install -g pm2 --quiet
    "
    echo "   PM2 ter-install"
fi

# ---------------------------------------------------------------------------
# 9. Restart PM2
# ---------------------------------------------------------------------------
echo ">> Restart PM2..."
PM2_RUNNING=$(ssh "$VPS" "pm2 describe stock-api > /dev/null 2>&1 && echo yes || echo no")

if [ "$PM2_RUNNING" = "no" ]; then
    echo "   Start PM2 pertama kali..."
    ssh "$VPS" "pm2 start $APP_DIR/ecosystem.config.js && pm2 save"
else
    ssh "$VPS" "pm2 delete stock-api && pm2 start $APP_DIR/ecosystem.config.js && pm2 save"
fi
echo "   PM2 running"

# ---------------------------------------------------------------------------
# 8. Bootstrap IDX (opsional)
# ---------------------------------------------------------------------------
if [ "$WITH_BOOTSTRAP" = "true" ]; then
    echo ""
    echo ">> Trigger IDX bootstrap (background, ~30 menit)..."
    ssh "$VPS" "cd $API_DIR && nohup $VENV/python -m app.ingestion.idx_full_bootstrap > $APP_DIR/logs/bootstrap.log 2>&1 &"
    echo "   Bootstrap dijalankan di background"
    echo "   Monitor: ssh $VPS 'tail -f $APP_DIR/logs/bootstrap.log'"
fi

# ---------------------------------------------------------------------------
# 9. Verifikasi
# ---------------------------------------------------------------------------
echo ""
echo ">> Cek status API..."
sleep 3
HTTP_STATUS=$(ssh "$VPS" "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health || echo 000")

echo ""
echo "=================================="
if [ "$HTTP_STATUS" = "200" ]; then
    echo "DEPLOY BERHASIL"
    echo "API: http://$VPS_IP:8000"
    echo "Health: $HTTP_STATUS OK"
else
    echo "API belum merespons (status: $HTTP_STATUS)"
    echo "Cek log: ssh $VPS 'pm2 logs stock-api --lines 30'"
fi
echo "=================================="
echo ""
echo "Perintah berguna:"
echo "  ssh $VPS 'pm2 status'"
echo "  ssh $VPS 'pm2 logs stock-api --lines 50'"
echo "  ssh $VPS 'pm2 restart stock-api'"
