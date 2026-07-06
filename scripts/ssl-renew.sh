#!/usr/bin/env bash
# =============================================================================
# scripts/ssl-renew.sh — renew Let's Encrypt certificates via certbot and
# reload nginx so the new certificate is picked up without downtime.
#
# Designed to be run from cron (see nginx/ssl/README.md). Uses the webroot
# challenge served by the edge nginx from /var/www/certbot.
#
# Usage:
#   scripts/ssl-renew.sh
#
# Environment:
#   COMPOSE_PROJECT_NAME   docker compose project name (default: mudir)
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-mudir}"

log() { printf '\033[1;34m[ssl-renew]\033[0m %s\n' "$*"; }

log "Attempting certificate renewal via certbot..."
# Run certbot in a one-shot container sharing the cert + webroot volumes with
# the edge nginx. `renew` is a no-op unless a cert is within 30 days of expiry.
docker run --rm \
  -v "${COMPOSE_PROJECT_NAME}_nginx_certs:/etc/letsencrypt" \
  -v "${COMPOSE_PROJECT_NAME}_nginx_acme:/var/www/certbot" \
  certbot/certbot renew --webroot -w /var/www/certbot --quiet

log "Reloading nginx to apply any renewed certificates..."
docker compose exec -T nginx nginx -s reload || \
  docker compose restart nginx

log "SSL renewal check complete."
