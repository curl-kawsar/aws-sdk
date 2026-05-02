#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# MinIO Upload Service — VPS bootstrap script
# Run once on a fresh Ubuntu/Debian VPS as root (or with sudo):
#   bash deploy/setup.sh
# ──────────────────────────────────────────────────────────────────────

DOMAIN="upload.1550plus.com"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Updating system packages"
apt-get update -qq && apt-get upgrade -y -qq

echo "==> Installing Docker (if missing)"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

echo "==> Installing Nginx and Certbot (if missing)"
apt-get install -y -qq nginx certbot python3-certbot-nginx

echo "==> Configuring firewall (ufw)"
if command -v ufw &>/dev/null; then
    ufw allow 22/tcp   # SSH
    ufw allow 80/tcp   # HTTP (redirect + ACME)
    ufw allow 443/tcp  # HTTPS
    ufw --force enable
    echo "    Firewall: 22, 80, 443 open. API/MinIO only on localhost (see .env ports)."
fi

MINIO_CONSOLE_PORT="$(grep -E '^MINIO_HOST_PORT_CONSOLE=' "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true)"
MINIO_CONSOLE_PORT="${MINIO_CONSOLE_PORT:-29001}"

echo "==> Installing Nginx site config"
cp "$PROJECT_DIR/deploy/nginx/upload-api.conf" "/etc/nginx/sites-available/$DOMAIN"
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> Obtaining TLS certificate via Let's Encrypt"
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect \
    --email "admin@$DOMAIN" || echo "    (certbot may need manual run if DNS is not yet pointing here)"

echo "==> Starting Docker Compose (production overlay)"
cd "$PROJECT_DIR"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Done!  https://$DOMAIN should now be live."
echo ""
echo "  API key (from .env):  $(grep '^API_KEYS=' .env | cut -d= -f2-)"
echo ""
echo "  Health check:  curl -s https://$DOMAIN/health"
echo "  MinIO console: ssh -L ${MINIO_CONSOLE_PORT}:127.0.0.1:${MINIO_CONSOLE_PORT} root@YOUR_VPS_IP"
echo "                 then open http://localhost:${MINIO_CONSOLE_PORT}"
echo "════════════════════════════════════════════════════════════════"
