#!/usr/bin/env bash
# =============================================================================
# scripts/update.sh — near zero-downtime update of the running stack.
#
# 1. Pull the latest code (git).
# 2. Take a database backup (safety net for rollback).
# 3. Build the new images.
# 4. Recreate services one at a time (rolling) so the edge stays up.
# 5. Verify health; roll back to the previous git revision on failure.
#
# Usage:
#   scripts/update.sh [gpu|cpu]        # default: gpu
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

PROFILE="${1:-gpu}"
case "$PROFILE" in
  gpu) OVERLAY="docker-compose.gpu.yml" ;;
  cpu) OVERLAY="docker-compose.cpu.yml" ;;
  *) echo "Usage: $0 [gpu|cpu]" >&2; exit 2 ;;
esac
COMPOSE="docker compose -f docker-compose.yml -f $OVERLAY"

log() { printf '\033[1;34m[update]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[update:ERROR]\033[0m %s\n' "$*" >&2; }

PREV_REV="$(git rev-parse HEAD 2>/dev/null || echo '')"

rollback() {
  err "Update failed — rolling back to ${PREV_REV}."
  [ -n "$PREV_REV" ] && git reset --hard "$PREV_REV" || true
  $COMPOSE up -d --build
}
trap 'rollback; exit 1' ERR

# ---- 1. Pull latest code ----------------------------------------------------
log "Fetching latest code..."
git fetch --all --prune
git pull --ff-only

# ---- 2. Safety backup -------------------------------------------------------
if [ -x scripts/backup.sh ]; then
  log "Taking a pre-update backup..."
  scripts/backup.sh || err "Backup failed — continuing (review manually)."
fi

# ---- 3. Build ---------------------------------------------------------------
log "Building updated images..."
$COMPOSE build

# ---- 4. Rolling recreate ----------------------------------------------------
# Stateless app services first (rolling), leaving data services untouched.
for svc in backend frontend nginx; do
  log "Recreating service: $svc"
  $COMPOSE up -d --no-deps --build "$svc"
  sleep 5
done

# ---- 5. Verify --------------------------------------------------------------
log "Verifying health..."
deadline=$(( $(date +%s) + 180 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  bad=$($COMPOSE ps --format '{{.Name}} {{.Health}}' 2>/dev/null \
    | awk '$2 != "" && $2 != "healthy" {print $1}' || true)
  [ -z "$bad" ] && { log "Update complete — all services healthy."; trap - ERR; exit 0; }
  sleep 5
done

err "Health check timed out: $bad"
exit 1
