# ORCHESTRA AI services

Self-hosted, open-source AI services that power the ORCHESTRA coordinator. They
use the models installed by [`../auto-install.sh`](../auto-install.sh) and talk
only to local runtimes (Ollama, ChromaDB) — **no external AI APIs**.

## Modules

| File                     | Purpose                                             |
|--------------------------|-----------------------------------------------------|
| `config.py`              | Central config, env loading, hardware detection     |
| `llm_service.py`         | Ollama LLM — the main orchestrator / "AI brain"     |
| `whisper_service.py`     | Offline voice transcription via whisper.cpp         |
| `embeddings_service.py`  | BGE-M3 text embeddings + cosine similarity          |
| `vector_db_service.py`   | ChromaDB long-term memory (`orchestra_memory`)      |
| `sentiment_service.py`   | Arabic sentiment / urgency detection                |
| `translation_service.py` | NLLB-200 Arabic ↔ English translation (optional)    |
| `requirements.txt`       | Python dependencies                                 |

## Install

```bash
# 1. Install models + runtimes (Ollama, ChromaDB, venv, PyTorch)
../auto-install.sh

# 2. Install the Python service dependencies into that venv
source ~/.orchestra/venv/bin/activate
pip install -r requirements.txt
```

`auto-install.sh` installs the correct CPU/CUDA PyTorch build automatically
based on detected hardware. Install `torch` **before** `requirements.txt` if you
set up the environment manually.

## Usage

Each service exposes both a class and module-level convenience functions, and a
shared lazily-initialised singleton via `get_service()`:

```python
from orchestra.services import llm_service, sentiment_service
from orchestra.services import vector_db_service, embeddings_service

# Understand an incoming message (structured JSON)
intent = llm_service.understand_intent("متى يخلص تجهيز المتجر؟")
# {"intent": "...", "entities": {...}, "sentiment": "...", "urgency": "..."}

# Detect frustration / urgency
mood = sentiment_service.analyze("العميل زعلان والمشروع متأخر")

# Store and recall long-term memory
vec = embeddings_service.generate_embedding("Store opening delayed to Sunday")
vector_db_service.store("evt-1", "Store opening delayed to Sunday", {"project": "riyadh"}, vec)
hits = vector_db_service.search(vec, limit=5)
```

The **LLM service is the primary orchestrator**: it understands messages,
extracts workflows, generates replies and summaries, and other services
(embeddings, vector memory, sentiment, transcription, translation) feed it
context.

## Configuration

All settings come from environment variables with defaults matching
`auto-install.sh`. See `config.py` for the full list. Key variables:

| Variable              | Default                        | Purpose                    |
|-----------------------|--------------------------------|----------------------------|
| `OLLAMA_HOST`         | `127.0.0.1:11434`              | Ollama API host            |
| `ORCHESTRA_LLM_MODEL` | `llama3:8b-instruct-q4_K_M`    | LLM tag (from auto-install)|
| `WHISPER_CPP_BINARY`  | `whisper-cli`                  | whisper.cpp binary         |
| `WHISPER_MODEL_PATH`  | `./models/ggml-base.bin`       | GGML whisper model         |
| `EMBEDDING_MODEL`     | `./models/bge-m3`              | BGE-M3 model path          |
| `CHROMA_HOST`/`PORT`  | `127.0.0.1` / `8000`           | ChromaDB endpoint          |
| `SENTIMENT_MODEL`     | `./models/arabic-sentiment`    | Arabic sentiment model     |
| `TRANSLATION_MODEL`   | `facebook/nllb-200-distilled-600M` | NLLB-200 model         |
| `ORCHESTRA_GPU`       | *(auto-detected)*              | Force GPU on/off           |

## Notes

- ML libraries are imported lazily, so importing a service (and running
  `config`) works even before the heavy dependencies are installed.
- `whisper_service.transcribe_whatsapp_voice` validates media URLs against an
  allow-list of Twilio hosts to prevent SSRF, mirroring the Node backend.
