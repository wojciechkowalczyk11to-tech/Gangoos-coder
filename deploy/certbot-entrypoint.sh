#!/bin/bash
# Certbot entrypoint for Let's Encrypt SSL certificate management
#
# This runs in the certbot container and:
#   1. Issues initial certificate (if needed)
#   2. Sets up auto-renewal every 12 hours
#   3. Reloads Nginx after renewal

DOMAIN="${DOMAIN:-localhost}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-admin@example.com}"
CERTBOT_DIR="/etc/letsencrypt"

echo "[certbot] Domain: $DOMAIN"
echo "[certbot] Email: $LETSENCRYPT_EMAIL"

# ────────────────────────────────────────────────────────────────────────────
# Initial certificate issuance (if not already present)
# ────────────────────────────────────────────────────────────────────────────

CERT_PATH="$CERTBOT_DIR/live/$DOMAIN/fullchain.pem"

if [ ! -f "$CERT_PATH" ]; then
    echo "[certbot] Issuing initial certificate for $DOMAIN..."

    # Wait for Nginx to be ready
    sleep 5

    certbot certonly \
        --webroot \
        -w /var/www/certbot \
        -d "$DOMAIN" \
        --email "$LETSENCRYPT_EMAIL" \
        --agree-tos \
        --non-interactive \
        --quiet

    if [ -f "$CERT_PATH" ]; then
        echo "[certbot] Certificate issued successfully"
    else
        echo "[certbot] WARNING: Certificate issuance failed"
    fi
else
    echo "[certbot] Certificate already exists at $CERT_PATH"
fi

# ────────────────────────────────────────────────────────────────────────────
# Renewal loop
# ────────────────────────────────────────────────────────────────────────────

echo "[certbot] Starting renewal loop (checking every 12 hours)..."

while true; do
    sleep 43200  # 12 hours

    echo "[certbot] Checking for certificate renewal..."

    certbot renew \
        --webroot \
        -w /var/www/certbot \
        --quiet

    # Reload Nginx configuration
    echo "[certbot] Reloading Nginx..."
    docker exec nginx nginx -s reload || true

done
