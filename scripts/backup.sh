#!/usr/bin/env bash
# =============================================================================
# scripts/backup.sh — back up Mudir / ORCHESTRA persistent state.
#
# Backs up:
#   - PostgreSQL       (pg_dump, gzipped)
#   - ChromaDB         (data volume tarball)
#   - Ollama models    (optional — large; enable with BACKUP_MODELS=true)
#
# Optionally uploads to cloud storage (S3-compatible) and enforces a retention
# policy on the local backup directory.
#
# Usage:
#   scripts/backup.sh
#
# Environment:
#   BACKUP_DIR         local backup destination (default: ./backups)
#   RETENTION_DAYS     delete local backups older than this (default: 7)
#   BACKUP_MODELS      "true" to also archive Ollama models (default: false)
#   S3_BUCKET          optional s3://bucket/prefix target (needs awscli)
#   POSTGRES_USER / POSTGRES_DB   from .env
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
# Load .env if present so POSTGRES_* are available.
[ -f .env ] && set -a && . ./.env && set +a

COMPOSE="docker compose"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
BACKUP_MODELS="${BACKUP_MODELS:-false}"
POSTGRES_USER="${POSTGRES_USER:-mudir}"
POSTGRES_DB="${POSTGRES_DB:-mudir}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${BACKUP_DIR}/${STAMP}"

log() { printf '\033[1;34m[backup]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[backup:ERROR]\033[0m %s\n' "$*" >&2; }

mkdir -p "$DEST"

# ---- PostgreSQL -------------------------------------------------------------
log "Dumping PostgreSQL database '${POSTGRES_DB}'..."
$COMPOSE exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | gzip > "${DEST}/postgres-${POSTGRES_DB}.sql.gz"

# ---- ChromaDB ---------------------------------------------------------------
log "Archiving ChromaDB data volume..."
$COMPOSE run --rm --no-deps -T \
  -v "$(pwd)/${DEST}:/backup" chromadb \
  sh -c 'tar czf /backup/chromadb.tar.gz -C /chroma/chroma .' \
  2>/dev/null || err "ChromaDB archive failed (is the service defined?)"

# ---- Ollama models (optional) ----------------------------------------------
if [ "$BACKUP_MODELS" = "true" ]; then
  log "Archiving Ollama models (this may be large)..."
  $COMPOSE run --rm --no-deps -T \
    -v "$(pwd)/${DEST}:/backup" ollama \
    sh -c 'tar czf /backup/ollama-models.tar.gz -C /root/.ollama .' \
    2>/dev/null || err "Ollama model archive failed"
fi

# ---- Checksums --------------------------------------------------------------
( cd "$DEST" && sha256sum ./* > SHA256SUMS 2>/dev/null || true )
log "Backup written to ${DEST}"

# ---- Cloud upload (optional) ------------------------------------------------
if [ -n "${S3_BUCKET:-}" ]; then
  if command -v aws >/dev/null 2>&1; then
    log "Uploading to ${S3_BUCKET}/${STAMP}/ ..."
    aws s3 cp --recursive "$DEST" "${S3_BUCKET%/}/${STAMP}/"
  else
    err "S3_BUCKET set but awscli not installed — skipping upload."
  fi
fi

# ---- Retention --------------------------------------------------------------
log "Applying retention policy (${RETENTION_DAYS} days)..."
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" \
  -exec rm -rf {} + 2>/dev/null || true

log "Backup complete."
