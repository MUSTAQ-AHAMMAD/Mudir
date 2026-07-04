"""Central configuration for the ORCHESTRA self-hosted AI services.

All settings are sourced from environment variables (with sensible defaults
that match ``orchestra/auto-install.sh``) so the services can run without any
external AI APIs. Import the module-level :data:`config` singleton:

    from orchestra.services.config import config

    print(config.ollama_base_url)

The configuration also performs a best-effort hardware detection (GPU / RAM /
CPU) so that services can pick an appropriate compute device at runtime.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_LOG_LEVEL = os.getenv("ORCHESTRA_LOG_LEVEL", "INFO").upper()


def configure_logging() -> None:
    """Configure root logging once, honouring ``ORCHESTRA_LOG_LEVEL``.

    Safe to call multiple times; only the first call installs handlers.
    """

    if logging.getLogger().handlers:
        logging.getLogger().setLevel(_LOG_LEVEL)
        return
    logging.basicConfig(
        level=_LOG_LEVEL,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for ``name``."""

    configure_logging()
    return logging.getLogger(name)


_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning("Invalid int for %s=%r; using default %s", name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _detect_gpu() -> tuple[bool, int]:
    """Return ``(gpu_available, vram_megabytes)`` using ``nvidia-smi``.

    Falls back to ``(False, 0)`` when no NVIDIA GPU / driver is present. An
    explicit ``ORCHESTRA_GPU`` / ``ORCHESTRA_GPU_MEMORY`` override short-circuits
    detection (useful in CI or containers).
    """

    override = os.getenv("ORCHESTRA_GPU")
    if override is not None:
        available = override.strip().lower() in {"1", "true", "yes", "on"}
        return available, _env_int("ORCHESTRA_GPU_MEMORY", 0)

    if shutil.which("nvidia-smi") is None:
        return False, 0
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:  # pragma: no cover
        _log.debug("nvidia-smi failed: %s", exc)
        return False, 0
    first = out.stdout.strip().splitlines()
    if not first:
        return False, 0
    try:
        vram = int(first[0].strip())
    except ValueError:
        return False, 0
    return vram > 0, vram


def _detect_ram_gb() -> int:
    """Return total system RAM in GB (best effort, 0 when unknown)."""

    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int((pages * page_size) / (1024**3))
    except (ValueError, OSError, AttributeError):  # pragma: no cover
        return 0


def _detect_cpu_cores() -> int:
    return os.cpu_count() or 1


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Config:
    """Immutable configuration for all ORCHESTRA services."""

    # -- Paths ---------------------------------------------------------------
    orchestra_home: Path = field(
        default_factory=lambda: Path(
            _env("ORCHESTRA_HOME", str(Path.home() / ".orchestra"))
        )
    )
    models_dir: Path = field(
        default_factory=lambda: Path(_env("ORCHESTRA_MODELS_DIR", "./models"))
    )

    # -- Ollama (LLM) --------------------------------------------------------
    ollama_host: str = field(default_factory=lambda: _env("OLLAMA_HOST", "127.0.0.1:11434"))
    llm_model: str = field(
        default_factory=lambda: _env("ORCHESTRA_LLM_MODEL", "llama3:8b-instruct-q4_K_M")
    )
    llm_timeout: int = field(default_factory=lambda: _env_int("ORCHESTRA_LLM_TIMEOUT", 120))
    llm_max_retries: int = field(
        default_factory=lambda: _env_int("ORCHESTRA_LLM_MAX_RETRIES", 3)
    )

    # -- Whisper (voice) -----------------------------------------------------
    whisper_binary: str = field(
        default_factory=lambda: _env("WHISPER_CPP_BINARY", "whisper-cli")
    )
    whisper_model_path: str = field(
        default_factory=lambda: _env("WHISPER_MODEL_PATH", "./models/ggml-base.bin")
    )
    whisper_language: str = field(default_factory=lambda: _env("WHISPER_LANGUAGE", "ar"))

    # -- Embeddings (BGE-M3) -------------------------------------------------
    embedding_model: str = field(
        default_factory=lambda: _env("EMBEDDING_MODEL", "./models/bge-m3")
    )

    # -- Vector DB (ChromaDB) ------------------------------------------------
    chroma_host: str = field(default_factory=lambda: _env("CHROMA_HOST", "127.0.0.1"))
    chroma_port: int = field(default_factory=lambda: _env_int("CHROMA_PORT", 8000))
    chroma_collection: str = field(
        default_factory=lambda: _env("CHROMA_COLLECTION", "orchestra_memory")
    )

    # -- Sentiment -----------------------------------------------------------
    sentiment_model: str = field(
        default_factory=lambda: _env("SENTIMENT_MODEL", "./models/arabic-sentiment")
    )

    # -- Translation (NLLB-200) ---------------------------------------------
    translation_model: str = field(
        default_factory=lambda: _env(
            "TRANSLATION_MODEL", "facebook/nllb-200-distilled-600M"
        )
    )

    # -- Hardware (auto-detected; overridable via env) ----------------------
    gpu_available: bool = field(default_factory=lambda: _detect_gpu()[0])
    gpu_memory_mb: int = field(default_factory=lambda: _detect_gpu()[1])
    total_ram_gb: int = field(default_factory=_detect_ram_gb)
    cpu_cores: int = field(default_factory=_detect_cpu_cores)

    # -- Derived properties --------------------------------------------------
    @cached_property
    def ollama_base_url(self) -> str:
        """Full base URL for the Ollama HTTP API."""

        host = self.ollama_host
        if host.startswith(("http://", "https://")):
            return host.rstrip("/")
        return f"http://{host}"

    @cached_property
    def chroma_url(self) -> str:
        """Full base URL for the ChromaDB HTTP API."""

        return f"http://{self.chroma_host}:{self.chroma_port}"

    @cached_property
    def torch_device(self) -> str:
        """Preferred torch device string (``"cuda"`` or ``"cpu"``)."""

        return "cuda" if self.gpu_available else "cpu"

    def resolve_model_path(self, path_or_name: str) -> str:
        """Resolve a model reference.

        A value that looks like a local path (contains ``/`` or ``.`` and exists
        on disk) is returned as an absolute path; otherwise it is treated as a
        HuggingFace repo id / Ollama tag and returned unchanged.
        """

        candidate = Path(path_or_name)
        if candidate.exists():
            return str(candidate.resolve())
        return path_or_name

    def summary(self) -> dict:
        """Return a JSON-serialisable snapshot of the effective configuration."""

        return {
            "ollama_base_url": self.ollama_base_url,
            "llm_model": self.llm_model,
            "whisper_binary": self.whisper_binary,
            "whisper_model_path": self.whisper_model_path,
            "whisper_language": self.whisper_language,
            "embedding_model": self.embedding_model,
            "chroma_url": self.chroma_url,
            "chroma_collection": self.chroma_collection,
            "sentiment_model": self.sentiment_model,
            "translation_model": self.translation_model,
            "hardware": {
                "gpu_available": self.gpu_available,
                "gpu_memory_mb": self.gpu_memory_mb,
                "total_ram_gb": self.total_ram_gb,
                "cpu_cores": self.cpu_cores,
                "torch_device": self.torch_device,
            },
        }


# Module-level singleton used across all services.
config = Config()


def reload_config() -> Config:
    """Rebuild the singleton from the current environment and return it.

    Primarily useful in tests that mutate ``os.environ``.
    """

    global config
    config = Config()
    return config


__all__ = ["Config", "config", "reload_config", "get_logger", "configure_logging"]
