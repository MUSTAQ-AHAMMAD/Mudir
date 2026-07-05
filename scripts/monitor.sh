#!/usr/bin/env bash
# =============================================================================
# scripts/monitor.sh — quick health/resource snapshot of the stack.
#
# Reports:
#   - per-service container health
#   - HTTP health endpoints (backend /health, ChromaDB heartbeat, Ollama)
#   - host disk usage
#   - host memory usage
#   - GPU usage (if nvidia-smi is available)
# Exits non-zero (and optionally alerts) if anything looks unhealthy.
#
# Usage:
#   scripts/monitor.sh
#
# Environment:
#   DISK_THRESHOLD   percent usage that triggers an alert (default: 85)
#   MEM_THRESHOLD    percent usage that triggers an alert (default: 90)
#   NOTIFY_WEBHOOK   optional URL to POST alerts to
# =============================================================================
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

COMPOSE="docker compose"
DISK_THRESHOLD="${DISK_THRESHOLD:-85}"
MEM_THRESHOLD="${MEM_THRESHOLD:-90}"
PROBLEMS=0

log()  { printf '\033[1;34m[monitor]\033[0m %s\n' "$*"; }
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[1;31m✗\033[0m %s\n' "$*"; PROBLEMS=$((PROBLEMS+1)); }

alert() {
  [ -z "${NOTIFY_WEBHOOK:-}" ] && return 0
  curl -fsS -X POST -H 'Content-Type: application/json' \
    -d "{\"text\":\"[Mudir monitor] $*\"}" "$NOTIFY_WEBHOOK" >/dev/null 2>&1 || true
}

# ---- Container health -------------------------------------------------------
log "Service health:"
$COMPOSE ps --format '{{.Name}} {{.State}} {{.Health}}' 2>/dev/null | while read -r name state health; do
  if [ "$health" = "healthy" ] || { [ -z "$health" ] && [ "$state" = "running" ]; }; then
    ok "$name ($state${health:+/$health})"
  else
    warn "$name ($state${health:+/$health})"
  fi
done
# Recount problems in the parent shell (the while ran in a subshell above).
BAD=$($COMPOSE ps --format '{{.Name}} {{.Health}}' 2>/dev/null \
  | awk '$2 != "" && $2 != "healthy" {print $1}' || true)
[ -n "$BAD" ] && { PROBLEMS=$((PROBLEMS+1)); alert "Unhealthy services: $BAD"; }

# ---- HTTP endpoints ---------------------------------------------------------
log "Endpoint checks:"
if $COMPOSE exec -T backend wget -qO- http://localhost:3000/health >/dev/null 2>&1; then
  ok "backend /health"
else
  warn "backend /health unreachable"; alert "backend /health failed"
fi
if $COMPOSE exec -T chromadb wget -qO- http://localhost:8000/api/v1/heartbeat >/dev/null 2>&1; then
  ok "chromadb heartbeat"
else
  warn "chromadb heartbeat unreachable"
fi
if $COMPOSE exec -T ollama ollama list >/dev/null 2>&1; then
  ok "ollama responding"
else
  warn "ollama not responding"
fi

# ---- Disk -------------------------------------------------------------------
log "Disk usage:"
DISK_PCT=$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')
if [ "${DISK_PCT:-0}" -ge "$DISK_THRESHOLD" ]; then
  warn "root filesystem at ${DISK_PCT}% (threshold ${DISK_THRESHOLD}%)"
  alert "Disk usage high: ${DISK_PCT}%"
else
  ok "root filesystem at ${DISK_PCT}%"
fi

# ---- Memory -----------------------------------------------------------------
log "Memory usage:"
if command -v free >/dev/null 2>&1; then
  MEM_PCT=$(free | awk '/^Mem:/ {printf "%d", ($2-$7)/$2*100}')
  if [ "${MEM_PCT:-0}" -ge "$MEM_THRESHOLD" ]; then
    warn "memory at ${MEM_PCT}% (threshold ${MEM_THRESHOLD}%)"
    alert "Memory usage high: ${MEM_PCT}%"
  else
    ok "memory at ${MEM_PCT}%"
  fi
else
  warn "'free' not available"
fi

# ---- GPU (optional) ---------------------------------------------------------
if command -v nvidia-smi >/dev/null 2>&1; then
  log "GPU usage:"
  nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total \
    --format=csv,noheader | while IFS= read -r line; do ok "GPU: $line"; done
else
  log "GPU: nvidia-smi not present (CPU-only host)."
fi

echo
if [ "$PROBLEMS" -eq 0 ]; then
  log "All checks passed."
  exit 0
fi
log "Detected ${PROBLEMS} problem(s)."
exit 1
