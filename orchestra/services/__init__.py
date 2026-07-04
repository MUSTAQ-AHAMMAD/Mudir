"""ORCHESTRA self-hosted AI services.

A collection of 100% self-hosted, open-source AI services that use the models
installed by ``orchestra/auto-install.sh``. No external AI APIs are used.

Services:
    - :mod:`config`               Central configuration + hardware detection
    - :mod:`llm_service`          Ollama LLM (main orchestrator)
    - :mod:`whisper_service`      Offline voice transcription (whisper.cpp)
    - :mod:`embeddings_service`   BGE-M3 text embeddings
    - :mod:`vector_db_service`    ChromaDB long-term memory
    - :mod:`sentiment_service`    Arabic sentiment / emotion detection
    - :mod:`translation_service`  NLLB-200 Arabic <-> English translation
"""

from __future__ import annotations

from .config import config, get_logger

__all__ = ["config", "get_logger"]
