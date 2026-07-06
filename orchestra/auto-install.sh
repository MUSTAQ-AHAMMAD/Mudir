#!/usr/bin/env bash
# auto-install.sh — ORCHESTRA self-hosted AI stack installer.
#
# Detects the host hardware (GPU / RAM / CPU), picks the largest models that
# will fit, installs every dependency, downloads the models, and starts all
# services. Everything runs locally — no external AI APIs (OpenAI, Google,
# Anthropic) are contacted at runtime.
#
# Stack (all open-source):
#   - Text LLM ............ Llama 3 / Phi-3 via Ollama
#   - Voice transcription . Whisper (faster-whisper)
#   - Embeddings .......... BGE-M3 (sentence-transformers)
#   - Vector DB ........... ChromaDB
#   - Translation ......... NLLB-200 (transformers)
#   - Sentiment ........... DistilBERT Arabic (transformers)
#   - OCR ................. Tesseract (with Arabic language pack)
#
# Usage:
#   ./auto-install.sh                 # detect + install + download + start
#   ./auto-install.sh --detect-only   # print the hardware/model plan and exit
#   ./auto-install.sh --skip-models    # install deps only, don't pull models
#   ./auto-install.sh --no-start       # install + download, don't start services
#   ./auto-install.sh --help
#
# Tested on Ubuntu 22.04 LTS. Re-running is safe (idempotent where possible).

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (override via environment variables)
# ---------------------------------------------------------------------------
ORCHESTRA_HOME="${ORCHESTRA_HOME:-$HOME/.orchestra}"
VENV_DIR="${VENV_DIR:-$ORCHESTRA_HOME/venv}"
CHROMA_HOST="${CHROMA_HOST:-127.0.0.1}"
CHROMA_PORT="${CHROMA_PORT:-8000}"
CHROMA_DATA_DIR="${CHROMA_DATA_DIR:-$ORCHESTRA_HOME/chroma}"
LOG_DIR="${LOG_DIR:-$ORCHESTRA_HOME/logs}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

# Behaviour flags (set by CLI parsing below).
DETECT_ONLY=false
SKIP_MODELS=false
START_SERVICES=true

# ---------------------------------------------------------------------------
# Pretty logging helpers
# ---------------------------------------------------------------------------
log()  { printf '%s\n' "$*"; }
info() { printf 'ℹ️  %s\n' "$*"; }
ok()   { printf '✅ %s\n' "$*"; }
warn() { printf '⚠️  %s\n' "$*" >&2; }
err()  { printf '❌ %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------
usage() {
  sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
  case "$arg" in
    --detect-only) DETECT_ONLY=true ;;
    --skip-models) SKIP_MODELS=true ;;
    --no-start)    START_SERVICES=false ;;
    -h|--help)     usage; exit 0 ;;
    *) die "Unknown option: $arg (try --help)" ;;
  esac
done

# ---------------------------------------------------------------------------
# 1. Hardware detection
# ---------------------------------------------------------------------------
GPU_AVAILABLE=false
GPU_MEMORY=0
TOTAL_RAM=0
CPU_CORES=1

detect_hardware() {
  log "🔍 Detecting hardware..."

  # GPU (NVIDIA CUDA). memory.total is reported in MiB.
  if command -v nvidia-smi >/dev/null 2>&1; then
    if GPU_MEMORY="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d '[:space:]')"; then
      if [[ "$GPU_MEMORY" =~ ^[0-9]+$ ]] && [ "$GPU_MEMORY" -gt 0 ]; then
        GPU_AVAILABLE=true
        ok "GPU detected (${GPU_MEMORY} MiB VRAM)."
      fi
    fi
  fi
  if [ "$GPU_AVAILABLE" != true ]; then
    GPU_MEMORY=0
    warn "No GPU detected. Running on CPU only."
  fi

  # RAM in GB.
  if command -v free >/dev/null 2>&1; then
    TOTAL_RAM="$(free -g | awk '/^Mem:/{print $2}')"
  fi
  [[ "$TOTAL_RAM" =~ ^[0-9]+$ ]] || TOTAL_RAM=0
  log "📊 Total RAM: ${TOTAL_RAM}GB"

  # CPU cores.
  if command -v nproc >/dev/null 2>&1; then
    CPU_CORES="$(nproc)"
  fi
  [[ "$CPU_CORES" =~ ^[0-9]+$ ]] || CPU_CORES=1
  log "📊 CPU Cores: ${CPU_CORES}"
}

# ---------------------------------------------------------------------------
# 2. Model selection (based on detected hardware)
# ---------------------------------------------------------------------------
LLM_MODEL=""
WHISPER_MODEL=""
WHISPER_COMPUTE=""
EMBEDDING_MODEL="BAAI/bge-m3"
TRANSLATION_MODEL="facebook/nllb-200-distilled-600M"
SENTIMENT_MODEL="CAMeL-Lab/bert-base-arabic-camelbert-da-sentiment"

select_models() {
  # Text LLM — prefer GPU tiers, then fall back to CPU-friendly quantisations.
  if [ "$GPU_AVAILABLE" = true ] && [ "$GPU_MEMORY" -ge 24000 ]; then
    LLM_MODEL="llama3:70b-instruct-q4_0"
  elif [ "$GPU_AVAILABLE" = true ] && [ "$GPU_MEMORY" -ge 6000 ]; then
    LLM_MODEL="llama3:8b-instruct-q4_0"
  elif [ "$TOTAL_RAM" -ge 32 ]; then
    LLM_MODEL="llama3:8b-instruct-q4_K_M"   # CPU only, higher quality quant
  else
    LLM_MODEL="phi3:3.8b-mini-instruct-4k-q4_0"  # Lightweight fallback
  fi

  # Whisper — a bigger model where there is VRAM/RAM headroom.
  if [ "$GPU_AVAILABLE" = true ] && [ "$GPU_MEMORY" -ge 6000 ]; then
    WHISPER_MODEL="medium"
    WHISPER_COMPUTE="float16"
  elif [ "$GPU_AVAILABLE" = true ]; then
    WHISPER_MODEL="small"
    WHISPER_COMPUTE="float16"
  elif [ "$TOTAL_RAM" -ge 16 ]; then
    WHISPER_MODEL="small"
    WHISPER_COMPUTE="int8"
  else
    WHISPER_MODEL="base"
    WHISPER_COMPUTE="int8"
  fi
}

print_plan() {
  log ""
  log "🧠 Selected model plan"
  log "   Text LLM ......... $LLM_MODEL"
  log "   Whisper .......... $WHISPER_MODEL (compute: $WHISPER_COMPUTE)"
  log "   Embeddings ....... $EMBEDDING_MODEL"
  log "   Translation ...... $TRANSLATION_MODEL"
  log "   Sentiment ........ $SENTIMENT_MODEL"
  log "   Vector DB ........ ChromaDB @ ${CHROMA_HOST}:${CHROMA_PORT}"
  log "   OCR .............. Tesseract (ara+eng)"
  log ""
}

# ---------------------------------------------------------------------------
# 3. Dependency installation
# ---------------------------------------------------------------------------
SUDO=""
require_sudo() {
  if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || die "Root privileges required (install sudo or run as root)."
    SUDO="sudo"
  fi
}

install_system_packages() {
  log "📦 Installing system packages..."
  require_sudo
  if ! command -v apt-get >/dev/null 2>&1; then
    warn "apt-get not found — install these manually: python3 python3-venv python3-pip ffmpeg tesseract-ocr tesseract-ocr-ara curl"
    return
  fi
  export DEBIAN_FRONTEND=noninteractive
  $SUDO apt-get update -y
  $SUDO apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    ffmpeg \
    tesseract-ocr tesseract-ocr-ara \
    curl ca-certificates
  ok "System packages installed."
}

install_ollama() {
  log "📦 Installing Ollama (LLM runtime)..."
  if command -v ollama >/dev/null 2>&1; then
    ok "Ollama already installed."
    return
  fi
  # Official install script; requires network access during setup only.
  curl -fsSL https://ollama.com/install.sh | sh
  command -v ollama >/dev/null 2>&1 || die "Ollama installation failed."
  ok "Ollama installed."
}

install_python_stack() {
  log "📦 Setting up Python virtual environment..."
  python3 -m venv "$VENV_DIR"
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  pip install --upgrade pip wheel

  # Install PyTorch — CUDA build when a GPU is present, CPU build otherwise.
  if [ "$GPU_AVAILABLE" = true ]; then
    pip install torch --index-url https://download.pytorch.org/whl/cu121
  else
    pip install torch --index-url https://download.pytorch.org/whl/cpu
  fi

  pip install \
    "chromadb" \
    "sentence-transformers" \
    "faster-whisper" \
    "transformers" \
    "sentencepiece" \
    "pytesseract" \
    "pillow"
  ok "Python stack installed in $VENV_DIR."
}

# ---------------------------------------------------------------------------
# 4. Model downloads
# ---------------------------------------------------------------------------
start_ollama_daemon() {
  # Ensure the Ollama server is running so we can pull models / serve requests.
  if curl -fsS "http://${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    return
  fi
  info "Starting Ollama daemon..."
  OLLAMA_HOST="$OLLAMA_HOST" nohup ollama serve >"$LOG_DIR/ollama.log" 2>&1 &
  for _ in $(seq 1 30); do
    curl -fsS "http://${OLLAMA_HOST}/api/tags" >/dev/null 2>&1 && return
    sleep 1
  done
  die "Ollama daemon did not become ready — see $LOG_DIR/ollama.log"
}

download_models() {
  log "📥 Downloading models (this can take a while on first run)..."
  start_ollama_daemon
  info "Pulling LLM: $LLM_MODEL"
  ollama pull "$LLM_MODEL"

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  info "Pre-fetching Whisper / embeddings / translation / sentiment weights..."
  WHISPER_MODEL="$WHISPER_MODEL" \
  WHISPER_COMPUTE="$WHISPER_COMPUTE" \
  EMBEDDING_MODEL="$EMBEDDING_MODEL" \
  TRANSLATION_MODEL="$TRANSLATION_MODEL" \
  SENTIMENT_MODEL="$SENTIMENT_MODEL" \
  python3 - <<'PY'
import os

whisper_model = os.environ["WHISPER_MODEL"]
whisper_compute = os.environ["WHISPER_COMPUTE"]
embedding_model = os.environ["EMBEDDING_MODEL"]
translation_model = os.environ["TRANSLATION_MODEL"]
sentiment_model = os.environ["SENTIMENT_MODEL"]

print(f"  → Whisper ({whisper_model}, {whisper_compute})")
from faster_whisper import WhisperModel
WhisperModel(whisper_model, device="cpu", compute_type=whisper_compute)

print(f"  → Embeddings ({embedding_model})")
from sentence_transformers import SentenceTransformer
SentenceTransformer(embedding_model)

print(f"  → Translation ({translation_model})")
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
AutoTokenizer.from_pretrained(translation_model)
AutoModelForSeq2SeqLM.from_pretrained(translation_model)

print(f"  → Sentiment ({sentiment_model})")
from transformers import AutoModelForSequenceClassification
AutoTokenizer.from_pretrained(sentiment_model)
AutoModelForSequenceClassification.from_pretrained(sentiment_model)

print("  All model weights cached.")
PY
  ok "Models downloaded."
}

# ---------------------------------------------------------------------------
# 5. Start services
# ---------------------------------------------------------------------------
start_services() {
  log "🚀 Starting services..."
  start_ollama_daemon
  ok "Ollama serving on http://${OLLAMA_HOST}"

  # ChromaDB vector database.
  if curl -fsS "http://${CHROMA_HOST}:${CHROMA_PORT}/api/v1/heartbeat" >/dev/null 2>&1; then
    ok "ChromaDB already running on ${CHROMA_HOST}:${CHROMA_PORT}"
  else
    info "Starting ChromaDB..."
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    nohup chroma run --host "$CHROMA_HOST" --port "$CHROMA_PORT" --path "$CHROMA_DATA_DIR" \
      >"$LOG_DIR/chroma.log" 2>&1 &
    for _ in $(seq 1 30); do
      curl -fsS "http://${CHROMA_HOST}:${CHROMA_PORT}/api/v1/heartbeat" >/dev/null 2>&1 && break
      sleep 1
    done
    if curl -fsS "http://${CHROMA_HOST}:${CHROMA_PORT}/api/v1/heartbeat" >/dev/null 2>&1; then
      ok "ChromaDB serving on ${CHROMA_HOST}:${CHROMA_PORT}"
    else
      warn "ChromaDB did not report healthy — see $LOG_DIR/chroma.log"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  mkdir -p "$ORCHESTRA_HOME" "$LOG_DIR" "$CHROMA_DATA_DIR"

  detect_hardware
  select_models
  print_plan

  if [ "$DETECT_ONLY" = true ]; then
    info "Detect-only mode — exiting without installing."
    exit 0
  fi

  install_system_packages
  install_ollama
  install_python_stack

  if [ "$SKIP_MODELS" = true ]; then
    warn "Skipping model downloads (--skip-models)."
  else
    download_models
  fi

  if [ "$START_SERVICES" = true ]; then
    start_services
  else
    info "Skipping service startup (--no-start)."
  fi

  log ""
  ok "ORCHESTRA setup complete."
  log "   LLM API .......... http://${OLLAMA_HOST}"
  log "   Vector DB ........ http://${CHROMA_HOST}:${CHROMA_PORT}"
  log "   Python venv ...... $VENV_DIR"
  log "   Logs ............. $LOG_DIR"
}

main "$@"
