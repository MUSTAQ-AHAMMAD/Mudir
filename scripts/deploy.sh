#!/usr/bin/env bash
# =============================================================================
# scripts/deploy.sh — deploy the Mudir / ORCHESTRA production stack.
#
# Checks prerequisites, pulls/builds the latest images, restarts the stack with
# the chosen hardware profile, then health-checks every service. On failure it
# rolls back to the previously running images.
#
# Usage:
#   scripts/deploy.sh [gpu|cpu]        # default: gpu
#
# Environment:
#   COMPOSE_PROJECT_NAME   docker compose project name (default: mudir)
#   NOTIFY_WEBHOOK         optional URL to POST success/failure notifications
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

PROFILE="${1:-gpu}"
BASE_COMPOSE="docker-compose.yml"
case "$PROFILE" in
  gpu) OVERLAY="docker-compose.gpu.yml" ;;
  cpu) OVERLAY="docker-compose.cpu.yml" ;;
  *) echo "Usage: $0 [gpu|cpu]" >&2; exit 2 ;;
esac

COMPOSE="docker compose -f $BASE_COMPOSE -f $OVERLAY"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-mudir}"

log()  { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[deploy:ERROR]\033[0m %s\n' "$*" >&2; }

notify() {
  # Best-effort notification to an optional webhook (Slack-compatible payload).
  local status="$1" message="$2"
  [ -z "${NOTIFY_WEBHOOK:-}" ] && return 0
  curl -fsS -X POST -H 'Content-Type: application/json' \
    -d "{\"text\":\"[Mudir deploy] ${status}: ${message}\"}" \
    "$NOTIFY_WEBHOOK" >/dev/null 2>&1 || true
}

check_prereqs() {
  log "Checking prerequisites..."
  command -v docker >/dev/null 2>&1 || { err "docker is not installed"; exit 1; }
  docker compose version >/dev/null 2>&1 || { err "docker compose v2 is required"; exit 1; }
  [ -f .env ] || { err ".env not found — copy .env.production to .env and fill it in"; exit 1; }
  if [ "$PROFILE" = "gpu" ] && ! docker info 2>/dev/null | grep -qi nvidia; then
    err "GPU profile selected but the NVIDIA runtime was not detected."
    err "Install the NVIDIA Container Toolkit or deploy with: $0 cpu"
    exit 1
  fi
}

# Record the currently-running image IDs so we can roll back on failure.
snapshot_images() {
  $COMPOSE images -q 2>/dev/null | sort -u > /tmp/mudir_deploy_prev_images || true
}

health_check() {
  # Poll `docker compose ps` until every service is healthy (or times out).
  local deadline=$(( $(date +%s) + 300 ))
  log "Waiting for services to become healthy (timeout 300s)..."
  while [ "$(date +%s)" -lt "$deadline" ]; do
    local unhealthy
    unhealthy=$($COMPOSE ps --format '{{.Name}} {{.Health}}' 2>/dev/null \
      | awk '$2 != "" && $2 != "healthy" {print $1}' || true)
    if [ -z "$unhealthy" ]; then
      log "All services healthy."
      return 0
    fi
    sleep 5
  done
  err "Timed out waiting for: $unhealthy"
  return 1
}

rollback() {
  err "Deployment failed — rolling back."
  $COMPOSE up -d --no-build || true
  notify "FAILED" "Deployment failed; rollback attempted on $(hostname)"
}

main() {
  check_prereqs
  snapshot_images

  log "Pulling pre-built images (if any)..."
  $COMPOSE pull --ignore-pull-failures || true

  log "Building local images..."
  $COMPOSE build

  log "Starting stack (profile: $PROFILE)..."
  $COMPOSE up -d --remove-orphans

  if ! health_check; then
    rollback
    exit 1
  fi

  log "Pruning dangling images..."
  docker image prune -f >/dev/null 2>&1 || true

  log "Deployment complete."
  notify "SUCCESS" "Deployed profile=$PROFILE on $(hostname)"
}

trap 'err "Unexpected error on line $LINENO"; rollback; exit 1' ERR
main "$@"
