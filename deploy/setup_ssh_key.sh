#!/usr/bin/env bash
# setup_ssh_key.sh — Setup SSH key sekali saja agar deploy tanpa password
# Jalankan SEKALI dari laptop sebelum deploy pertama.
# Setelah ini semua scp/ssh ke VPS tidak perlu password lagi.

set -euo pipefail

VPS_IP="${1:-163.245.208.211}"
VPS_USER="${2:-root}"
KEY_FILE="$HOME/.ssh/stock_intelligence_vps"

echo "=== Setup SSH Key untuk VPS Stock Intelligence ==="
echo "Target: $VPS_USER@$VPS_IP"
echo ""

# 1. Buat SSH key jika belum ada
if [ ! -f "$KEY_FILE" ]; then
    echo ">> Membuat SSH key baru (ed25519)..."
    ssh-keygen -t ed25519 -f "$KEY_FILE" -C "stock-intelligence-deploy" -N ""
    echo "   Key dibuat: $KEY_FILE"
else
    echo ">> SSH key sudah ada: $KEY_FILE (skip generate)"
fi

echo ""
echo ">> Mengirim public key ke VPS (diperlukan password VPS SEKALI ini)..."
echo "   Ketik password VPS ketika diminta:"
echo ""

# 2. Copy public key ke VPS
ssh-copy-id -i "$KEY_FILE.pub" -o StrictHostKeyChecking=accept-new "$VPS_USER@$VPS_IP"

echo ""
echo ">> Menambahkan entry ke ~/.ssh/config..."

# 3. Tambah entry ke ~/.ssh/config agar tidak perlu -i setiap kali
SSH_CONFIG="$HOME/.ssh/config"
ENTRY="
# Stock Intelligence VPS (auto-added by setup_ssh_key.sh)
Host stock-vps
    HostName $VPS_IP
    User $VPS_USER
    IdentityFile $KEY_FILE
    StrictHostKeyChecking no
    ServerAliveInterval 60
"

if ! grep -q "Host stock-vps" "$SSH_CONFIG" 2>/dev/null; then
    echo "$ENTRY" >> "$SSH_CONFIG"
    chmod 600 "$SSH_CONFIG"
    echo "   Entry 'stock-vps' ditambahkan ke ~/.ssh/config"
else
    echo "   Entry 'stock-vps' sudah ada di ~/.ssh/config (skip)"
fi

echo ""
echo ">> Tes koneksi tanpa password..."
if ssh -i "$KEY_FILE" -o BatchMode=yes "$VPS_USER@$VPS_IP" "echo 'Koneksi berhasil!'" 2>/dev/null; then
    echo ""
    echo "=== BERHASIL! SSH key sudah terpasang ==="
    echo ""
    echo "Sekarang bisa deploy tanpa password:"
    echo "  bash deploy/deploy.sh"
    echo ""
    echo "Atau SSH langsung:"
    echo "  ssh stock-vps"
else
    echo ""
    echo "=== GAGAL — coba manual: ==="
    echo "  ssh-copy-id -i $KEY_FILE.pub $VPS_USER@$VPS_IP"
fi
