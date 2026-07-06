#!/usr/bin/env sh
# -----------------------------------------------------------------------------
# docker/ollama-entrypoint.sh — start the Ollama server and pre-pull models.
#
# 1. Launch `ollama serve` in the background.
# 2. Wait for the HTTP API to become responsive.
# 3. Pull every model listed in $OLLAMA_MODELS (comma/space separated).
# 4. Hand control back to the server process (PID 1 semantics via `wait`).
# -----------------------------------------------------------------------------
set -eu

: "${OLLAMA_MODELS:=llama3:8b}"

echo "[ollama-entrypoint] starting server..."
ollama serve &
SERVER_PID=$!

# Wait (up to ~60s) for the API to accept requests before pulling.
echo "[ollama-entrypoint] waiting for API..."
i=0
until ollama list >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "[ollama-entrypoint] server did not become ready in time" >&2
    break
  fi
  sleep 1
done

# Normalise the model list separators (commas -> spaces) and pull each one.
MODELS=$(echo "$OLLAMA_MODELS" | tr ',' ' ')
for model in $MODELS; do
  [ -z "$model" ] && continue
  echo "[ollama-entrypoint] pulling model: $model"
  ollama pull "$model" || echo "[ollama-entrypoint] WARN: failed to pull $model" >&2
done

echo "[ollama-entrypoint] ready — models pre-loaded."
# Keep the container alive on the server process.
wait "$SERVER_PID"
