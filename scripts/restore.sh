#!/usr/bin/env bash
# restore.sh — Restore dari backup dump yang dibuat backup.sh
#
# Penggunaan:
#   ./restore.sh <backup_file> [target_DATABASE_URL_SYNC]
#
#   <backup_file>  — path ke file .sql.gz atau .sql.gz.enc
#   [target_url]   — opsional; kalau tidak diset, pakai DATABASE_URL_SYNC dari env/.env
#
# Contoh:
#   ./restore.sh backups/stock_intel_20261104_120000.sql.gz.enc
#   ./restore.sh backups/stock_intel_20261104_120000.sql.gz postgres://user:pass@localhost/stock_intel_restore
#
# Env vars:
#   DATABASE_URL_SYNC      — target DB jika tidak ada argumen ke-2
#   BACKUP_ENCRYPTION_KEY  — passphrase AES-256 untuk file .enc

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
ENV_FILE="${SCRIPT_DIR}/../services/api/.env"
if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source <(grep -E '^[A-Z_]+=.+' "${ENV_FILE}" | sed 's/#.*//')
    set +a
fi

# ---------------------------------------------------------------------------
# Argumen
# ---------------------------------------------------------------------------
BACKUP_FILE="${1:-}"
TARGET_URL="${2:-${DATABASE_URL_SYNC:-}}"

if [[ -z "${BACKUP_FILE}" ]]; then
    echo "Penggunaan: $0 <backup_file> [target_DATABASE_URL_SYNC]" >&2
    echo "" >&2
    echo "Contoh:" >&2
    echo "  $0 backups/stock_intel_20261104_120000.sql.gz.enc" >&2
    exit 1
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "ERROR: File tidak ditemukan: ${BACKUP_FILE}" >&2
    exit 1
fi

if [[ -z "${TARGET_URL}" ]]; then
    echo "ERROR: DATABASE_URL_SYNC tidak diset dan tidak ada argumen ke-2." >&2
    exit 1
fi

if [[ "${TARGET_URL}" != postgres* && "${TARGET_URL}" != postgresql* ]]; then
    echo "ERROR: Restore hanya mendukung PostgreSQL." >&2
    exit 1
fi

if ! command -v psql &>/dev/null; then
    echo "ERROR: psql tidak ditemukan. Install postgresql-client." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Konfirmasi — operasi destructive
# ---------------------------------------------------------------------------
FILE_NAME="$(basename "${BACKUP_FILE}")"
echo ""
echo "========================================================"
echo "  PERINGATAN: Operasi ini akan MENIMPA data di database target."
echo "  File backup : ${FILE_NAME}"
echo "  Target DB   : $(echo "${TARGET_URL}" | sed 's/:\/\/[^@]*@/:\\/\\/***@/')"
echo "========================================================"
echo ""
read -r -p "Ketik 'yes' untuk melanjutkan: " CONFIRM
if [[ "${CONFIRM}" != "yes" ]]; then
    echo "Dibatalkan."
    exit 0
fi

# ---------------------------------------------------------------------------
# Verifikasi checksum jika ada
# ---------------------------------------------------------------------------
CHECKSUM_FILE="${BACKUP_FILE%.enc}.sha256"
if [[ ! -f "${CHECKSUM_FILE}" ]]; then
    # Coba nama alternatif (file .enc punya checksum dengan nama tanpa .enc)
    CHECKSUM_FILE="${BACKUP_FILE}.sha256"
fi
if [[ ! -f "${CHECKSUM_FILE}" ]]; then
    # Cari di direktori yang sama
    BASE_NAME="${FILE_NAME%.enc}"
    BASE_NAME="${BASE_NAME%.sql.gz}"
    CHECKSUM_FILE="$(dirname "${BACKUP_FILE}")/${BASE_NAME}.sha256"
fi

if [[ -f "${CHECKSUM_FILE}" ]]; then
    echo "[restore] Verifikasi checksum SHA256..."
    EXPECTED="$(cat "${CHECKSUM_FILE}")"
    ACTUAL="$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"
    if [[ "${EXPECTED}" != "${ACTUAL}" ]]; then
        echo "ERROR: Checksum tidak cocok! File mungkin rusak atau dimodifikasi." >&2
        echo "  Expected: ${EXPECTED}" >&2
        echo "  Actual  : ${ACTUAL}" >&2
        exit 1
    fi
    echo "[restore] Checksum OK"
else
    echo "[restore] WARNING: File checksum tidak ditemukan — integritas tidak diverifikasi." >&2
fi

# ---------------------------------------------------------------------------
# Dekripsi jika .enc
# ---------------------------------------------------------------------------
WORK_FILE="${BACKUP_FILE}"
TEMP_FILE=""

if [[ "${BACKUP_FILE}" == *.enc ]]; then
    if [[ -z "${BACKUP_ENCRYPTION_KEY:-}" ]]; then
        echo "ERROR: BACKUP_ENCRYPTION_KEY tidak diset — tidak bisa dekripsi." >&2
        exit 1
    fi
    TEMP_FILE="$(mktemp /tmp/stock_intel_restore_XXXXXXXX.sql.gz)"
    echo "[restore] Mendekripsi backup..."
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
        -pass "env:BACKUP_ENCRYPTION_KEY" \
        -in "${BACKUP_FILE}" \
        -out "${TEMP_FILE}"
    WORK_FILE="${TEMP_FILE}"
    echo "[restore] Dekripsi selesai"
fi

# ---------------------------------------------------------------------------
# Parse koneksi
# ---------------------------------------------------------------------------
RAW_URL="${TARGET_URL}"
RAW_URL="${RAW_URL%%+*}${RAW_URL#*//}"
RAW_URL="postgres://${RAW_URL#*//}"

read -r PG_USER PG_PASS PG_HOST PG_PORT PG_DB < <(python3 -c "
from urllib.parse import urlparse
u = urlparse('${RAW_URL}')
print(u.username or '', u.password or '', u.hostname or 'localhost', u.port or 5432, (u.path or '/').lstrip('/'))
")

# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------
echo "[restore] Memulai restore ke database '${PG_DB}'..."

export PGPASSWORD="${PG_PASS}"

gunzip -c "${WORK_FILE}" | psql \
    --host="${PG_HOST}" \
    --port="${PG_PORT}" \
    --username="${PG_USER}" \
    --dbname="${PG_DB}" \
    --no-password \
    --set ON_ERROR_STOP=1 \
    --quiet

unset PGPASSWORD

# Bersihkan temp file dekripsi
if [[ -n "${TEMP_FILE}" && -f "${TEMP_FILE}" ]]; then
    rm "${TEMP_FILE}"
fi

echo "[restore] Restore selesai — database '${PG_DB}' berhasil dipulihkan."
