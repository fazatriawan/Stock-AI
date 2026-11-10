#!/usr/bin/env bash
# backup.sh — PostgreSQL dump + enkripsi opsional
#
# Env vars yang dibaca (semua boleh di .env):
#   DATABASE_URL_SYNC  — postgres://user:pass@host:port/dbname  (wajib)
#   BACKUP_DIR         — direktori output             (default: ./backups)
#   BACKUP_RETENTION_DAYS — hapus backup lebih dari N hari (default: 30)
#   BACKUP_ENCRYPTION_KEY — passphrase AES-256; kosong = simpan plain (WARNING)
#
# Output:
#   {BACKUP_DIR}/stock_intel_YYYYMMDD_HHMMSS.sql.gz[.enc]
#   {BACKUP_DIR}/stock_intel_YYYYMMDD_HHMMSS.sha256
#
# Log: hanya nama file + ukuran + checksum. Path lengkap TIDAK dicetak
# agar credential/path sensitif tidak bocor ke stdout/syslog.

set -euo pipefail

# ---------------------------------------------------------------------------
# Load .env jika ada (dari direktori services/api)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../services/api/.env"
if [[ -f "${ENV_FILE}" ]]; then
    # Hanya export baris KEY=VALUE; abaikan komentar dan baris kosong
    set -a
    # shellcheck source=/dev/null
    source <(grep -E '^[A-Z_]+=.+' "${ENV_FILE}" | sed 's/#.*//')
    set +a
fi

# ---------------------------------------------------------------------------
# Validasi
# ---------------------------------------------------------------------------
if [[ -z "${DATABASE_URL_SYNC:-}" ]]; then
    echo "ERROR: DATABASE_URL_SYNC tidak diset. Set via env atau .env" >&2
    exit 1
fi

# Pastikan DATABASE_URL adalah PostgreSQL
if [[ "${DATABASE_URL_SYNC}" != postgres* && "${DATABASE_URL_SYNC}" != postgresql* ]]; then
    echo "ERROR: Backup hanya mendukung PostgreSQL. DATABASE_URL_SYNC bukan postgres://" >&2
    exit 1
fi

# Cek pg_dump tersedia
if ! command -v pg_dump &>/dev/null; then
    echo "ERROR: pg_dump tidak ditemukan. Install postgresql-client." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
BACKUP_DIR="${BACKUP_DIR:-${SCRIPT_DIR}/../backups}"
BACKUP_DIR="$(realpath "${BACKUP_DIR}")"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
BASE_NAME="stock_intel_${TIMESTAMP}"
DUMP_FILE="${BACKUP_DIR}/${BASE_NAME}.sql.gz"

mkdir -p "${BACKUP_DIR}"

# ---------------------------------------------------------------------------
# Parse koneksi dari DATABASE_URL_SYNC
# Format: postgres://user:pass@host:port/dbname atau
#         postgresql+asyncpg://...  (strip dialect)
# ---------------------------------------------------------------------------
RAW_URL="${DATABASE_URL_SYNC}"
# Strip dialect suffix seperti +asyncpg
RAW_URL="${RAW_URL%%+*}${RAW_URL#*//}"
RAW_URL="postgres://${RAW_URL#*//}"

# Ekstrak komponen via Python (lebih aman dari parsing manual)
read -r PG_USER PG_PASS PG_HOST PG_PORT PG_DB < <(python3 -c "
from urllib.parse import urlparse
u = urlparse('${RAW_URL}')
print(u.username or '', u.password or '', u.hostname or 'localhost', u.port or 5432, (u.path or '/').lstrip('/'))
")

if [[ -z "${PG_DB}" ]]; then
    echo "ERROR: Tidak bisa parse nama database dari DATABASE_URL_SYNC." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------
echo "[backup] Memulai dump database '${PG_DB}' → ${BASE_NAME}.sql.gz"

# PGPASSWORD di environment agar tidak muncul di process list
export PGPASSWORD="${PG_PASS}"

pg_dump \
    --host="${PG_HOST}" \
    --port="${PG_PORT}" \
    --username="${PG_USER}" \
    --no-password \
    --format=plain \
    --no-owner \
    --no-acl \
    "${PG_DB}" \
    | gzip -9 \
    > "${DUMP_FILE}"

unset PGPASSWORD

DUMP_SIZE="$(du -sh "${DUMP_FILE}" | cut -f1)"
echo "[backup] Dump selesai — ukuran: ${DUMP_SIZE}"

# ---------------------------------------------------------------------------
# Enkripsi (opsional)
# ---------------------------------------------------------------------------
if [[ -n "${BACKUP_ENCRYPTION_KEY:-}" ]]; then
    ENC_FILE="${DUMP_FILE}.enc"
    openssl enc -aes-256-cbc -pbkdf2 -iter 100000 \
        -pass "env:BACKUP_ENCRYPTION_KEY" \
        -in "${DUMP_FILE}" \
        -out "${ENC_FILE}"
    # Hapus plain dump setelah enkripsi berhasil
    rm "${DUMP_FILE}"
    FINAL_FILE="${ENC_FILE}"
    echo "[backup] File dienkripsi (AES-256-CBC)"
else
    FINAL_FILE="${DUMP_FILE}"
    echo "[backup] WARNING: BACKUP_ENCRYPTION_KEY tidak diset — file tersimpan plain. Set env var ini untuk produksi." >&2
fi

# ---------------------------------------------------------------------------
# Checksum SHA256
# ---------------------------------------------------------------------------
CHECKSUM_FILE="${BACKUP_DIR}/${BASE_NAME}.sha256"
sha256sum "${FINAL_FILE}" | awk '{print $1}' > "${CHECKSUM_FILE}"
CHECKSUM="$(cat "${CHECKSUM_FILE}")"

FINAL_NAME="$(basename "${FINAL_FILE}")"
echo "[backup] SHA256: ${CHECKSUM}  ${FINAL_NAME}"

# ---------------------------------------------------------------------------
# Cleanup backup lama
# ---------------------------------------------------------------------------
DELETED=0
while IFS= read -r old_file; do
    rm "${old_file}"
    DELETED=$((DELETED + 1))
done < <(find "${BACKUP_DIR}" -maxdepth 1 -name "stock_intel_*.gz*" -mtime "+${RETENTION_DAYS}" -type f 2>/dev/null)
# Hapus checksum file yang pasangan dump-nya sudah dihapus
while IFS= read -r old_sha; do
    base="${old_sha%.sha256}"
    if [[ ! -f "${base}.sql.gz" && ! -f "${base}.sql.gz.enc" ]]; then
        rm "${old_sha}"
    fi
done < <(find "${BACKUP_DIR}" -maxdepth 1 -name "stock_intel_*.sha256" -type f 2>/dev/null)

if [[ ${DELETED} -gt 0 ]]; then
    echo "[backup] Cleanup: ${DELETED} backup lama (>${RETENTION_DAYS} hari) dihapus"
fi

echo "[backup] Selesai — ${FINAL_NAME}"

# Tulis sentinel file untuk ops monitor
SENTINEL_FILE="${BACKUP_DIR}/.last_backup"
date -u +"%Y-%m-%dT%H:%M:%S+00:00" > "${SENTINEL_FILE}"
