#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# MinIO Upload Service — VPS bootstrap script
# Run from project root as root (or with sudo):
#   sudo bash deploy/setup.sh
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
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
    echo "    Firewall: 22, 80, 443 open. Block direct access to API port from WAN if needed (ufw deny API_PORT)."
fi

echo "==> Starting Docker Compose (API must be up before Nginx proxies)"
cd "$PROJECT_DIR"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo "==> Installing Nginx site (HTTP-only; valid before TLS certs exist)"
cp "$PROJECT_DIR/deploy/nginx/upload-api.conf" "/etc/nginx/sites-available/$DOMAIN"
ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> Obtaining TLS certificate (Certbot will extend this Nginx site with HTTPS)"
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect \
    --email "admin@$DOMAIN" || {
    echo ""
    echo "    Certbot failed (DNS must point here, port 80 open). Fix DNS then run:"
    echo "    sudo certbot --nginx -d $DOMAIN"
    echo ""
}

nginx -t && systemctl reload nginx

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Stack:  https://$DOMAIN  (after certbot) or http://$DOMAIN"
echo ""
echo "  API key:  $(grep '^API_KEYS=' "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2- || echo '(see .env)')"
echo ""
echo "  Health:  curl -s http://127.0.0.1:29002/health"
echo "           curl -s https://$DOMAIN/health"
echo ""
echo "  MinIO has no published host port. Admin CLI on VPS, e.g.:"
echo "    docker exec -it upload-minio mc alias set local http://localhost:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" --api S3v4"
echo "  (copy MINIO_ROOT_* from .env into the command, or: docker exec -it upload-minio sh)"
echo "════════════════════════════════════════════════════════════════"
