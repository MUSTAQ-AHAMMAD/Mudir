# ORCHESTRA — self-hosted AI stack

A 100% self-hosted, open-source AI stack that runs entirely on your own
hardware. No external AI APIs (OpenAI, Google, Anthropic) are contacted at
runtime — data never leaves your server and there are no per-token costs.

## Components (all open-source)

| Component            | Model / Tool                          | Runtime                |
|----------------------|---------------------------------------|------------------------|
| Text LLM             | Llama 3 (8B/70B) or Phi-3 fallback    | [Ollama](https://ollama.com) |
| Voice transcription  | Whisper                               | faster-whisper         |
| Embeddings           | BGE-M3                                | sentence-transformers  |
| Vector DB            | ChromaDB                              | chromadb               |
| Translation          | NLLB-200                              | transformers           |
| Sentiment            | Arabic BERT (DistilBERT-class)        | transformers           |
| OCR                  | Tesseract (with Arabic pack)          | pytesseract            |

## Auto-detection installer

[`auto-install.sh`](auto-install.sh) inspects the host hardware and picks the
largest models that fit:

1. **Detects** GPU (VRAM), total RAM, and CPU cores.
2. **Selects** appropriate models per hardware tier (GPU 24GB+ → Llama 3 70B,
   GPU 6GB+ → Llama 3 8B, 32GB+ RAM → Llama 3 8B CPU quant, otherwise Phi-3).
3. **Installs** system packages, Ollama, and a Python virtual environment
   (CUDA build of PyTorch when a GPU is present, CPU build otherwise).
4. **Downloads** the selected LLM and pre-fetches Whisper, embedding,
   translation, and sentiment weights.
5. **Starts** the Ollama LLM server and the ChromaDB vector database.

### Usage

```bash
./auto-install.sh                 # detect + install + download + start
./auto-install.sh --detect-only   # print the hardware/model plan and exit
./auto-install.sh --skip-models   # install dependencies only
./auto-install.sh --no-start      # install + download, don't start services
./auto-install.sh --help
```

Tested on **Ubuntu 22.04 LTS**. Re-running is safe (idempotent where possible).

### Configuration

Override defaults via environment variables:

| Variable          | Default                | Purpose                     |
|-------------------|------------------------|-----------------------------|
| `ORCHESTRA_HOME`  | `$HOME/.orchestra`     | Base data directory         |
| `VENV_DIR`        | `$ORCHESTRA_HOME/venv` | Python virtual environment  |
| `CHROMA_HOST`     | `127.0.0.1`            | ChromaDB bind host          |
| `CHROMA_PORT`     | `8000`                 | ChromaDB port               |
| `OLLAMA_HOST`     | `127.0.0.1:11434`      | Ollama API host             |

### After install

- LLM API: `http://127.0.0.1:11434`
- Vector DB: `http://127.0.0.1:8000`
- Logs: `$ORCHESTRA_HOME/logs`
