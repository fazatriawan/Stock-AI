#!/usr/bin/env bash
# migrate_db.sh — Dump database dari laptop, restore ke VPS
# Jalankan dari laptop, bukan dari VPS.
#
# Usage:
#   bash deploy/migrate_db.sh [VPS_IP] [VPS_USER]
#
# Contoh:
#   bash deploy/migrate_db.sh 163.245.208.211 root

set -euo pipefail

VPS_IP="${1:-163.245.208.211}"
VPS_USER="${2:-root}"
DUMP_FILE="/tmp/stock_intelligence_$(date +%Y%m%d_%H%M%S).sql"

echo "=== Migrasi Database: Laptop → VPS ==="
echo "VPS: $VPS_USER@$VPS_IP"
echo "File dump: $DUMP_FILE"
echo ""

# ---------------------------------------------------------------------------
# 1. Dump dari PostgreSQL lokal (laptop)
# ---------------------------------------------------------------------------
echo ">> Dump database lokal..."
# Pastikan DATABASE_URL_SYNC tersedia di environment atau hardcode di bawah
LOCAL_DB="${DATABASE_URL_SYNC:-postgresql://stock_user:change_me@localhost:5432/stock_intelligence}"

# Extract komponen dari URL
# Format: postgresql://user:password@host:port/dbname
DB_USER=$(echo "$LOCAL_DB" | sed 's|postgresql://\([^:]*\):.*|\1|')
DB_HOST=$(echo "$LOCAL_DB" | sed 's|.*@\([^:]*\):.*|\1|')
DB_PORT=$(echo "$LOCAL_DB" | sed 's|.*:\([0-9]*\)/.*|\1|')
DB_NAME=$(echo "$LOCAL_DB" | sed 's|.*/\([^?]*\).*|\1|')

PGPASSWORD=$(echo "$LOCAL_DB" | sed 's|.*://[^:]*:\([^@]*\)@.*|\1|') \
    pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" "$DB_NAME" \
    --no-owner --no-acl \
    -f "$DUMP_FILE"

echo "   Dump selesai: $(wc -l < "$DUMP_FILE") baris"

# ---------------------------------------------------------------------------
# 2. Upload ke VPS
# ---------------------------------------------------------------------------
echo ">> Upload ke VPS..."
scp "$DUMP_FILE" "$VPS_USER@$VPS_IP:/tmp/stock_dump.sql"

# ---------------------------------------------------------------------------
# 3. Restore di VPS
# ---------------------------------------------------------------------------
echo ">> Restore di VPS..."
ssh "$VPS_USER@$VPS_IP" bash <<'REMOTE'
set -euo pipefail

DUMP="/tmp/stock_dump.sql"
DB_NAME="stock_intelligence"
DB_USER="stock_user"

echo "   Dropping & recreating database..."
sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME};"
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"

echo "   Restoring..."
sudo -u postgres psql -U postgres "${DB_NAME}" < "$DUMP"

echo "   Selesai!"
rm -f "$DUMP"
REMOTE

# ---------------------------------------------------------------------------
# 4. Cleanup lokal
# ---------------------------------------------------------------------------
rm -f "$DUMP_FILE"

echo ""
echo "=== Migrasi selesai! ==="
echo "Verifikasi: ssh $VPS_USER@$VPS_IP 'sudo -u postgres psql stock_intelligence -c \"\\dt\"'"
