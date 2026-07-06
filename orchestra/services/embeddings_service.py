"""Embeddings service — text vectors via BGE-M3 (sentence-transformers).

Loads the locally downloaded BGE-M3 model (``./models/bge-m3`` by default) and
exposes helpers for single/batch embedding and cosine similarity. The model is
loaded lazily and cached for the lifetime of the service instance.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional, Sequence

from .config import config, get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sentence_transformers import SentenceTransformer

_log = get_logger(__name__)


class EmbeddingsServiceError(RuntimeError):
    """Raised when embeddings cannot be generated."""


class EmbeddingsService:
    """Generate embeddings with a locally hosted BGE-M3 model."""

    def __init__(self, model_path: Optional[str] = None, device: Optional[str] = None) -> None:
        self.model_path = model_path or config.embedding_model
        self.device = device or config.torch_device
        self._model: Optional["SentenceTransformer"] = None

    # -- model loading ------------------------------------------------------
    @property
    def model(self) -> "SentenceTransformer":
        """Lazily load and cache the SentenceTransformer model."""

        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover
                raise EmbeddingsServiceError(
                    "sentence-transformers is not installed; see requirements.txt"
                ) from exc
            resolved = config.resolve_model_path(self.model_path)
            _log.info("Loading embedding model %s on %s", resolved, self.device)
            try:
                self._model = SentenceTransformer(resolved, device=self.device)
            except Exception as exc:  # noqa: BLE001 - surface any load failure
                raise EmbeddingsServiceError(
                    f"Failed to load embedding model {resolved!r}: {exc}"
                ) from exc
        return self._model

    # -- public API ---------------------------------------------------------
    def generate_embedding(self, text: str) -> list[float]:
        """Convert a single string of text into an embedding vector."""

        if not isinstance(text, str) or not text.strip():
            raise EmbeddingsServiceError("text must be a non-empty string")
        return self.batch_generate_embeddings([text])[0]

    def batch_generate_embeddings(self, texts: Sequence[str]) -> list[list[float]]:
        """Convert multiple texts into embedding vectors in one batch."""

        if not texts:
            return []
        cleaned = [t if isinstance(t, str) else str(t) for t in texts]
        try:
            vectors = self.model.encode(
                cleaned,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingsServiceError(f"Embedding generation failed: {exc}") from exc
        return [vec.tolist() for vec in vectors]

    @staticmethod
    def cosine_similarity(vec1: Sequence[float], vec2: Sequence[float]) -> float:
        """Return the cosine similarity between two vectors in ``[-1, 1]``.

        Raises:
            EmbeddingsServiceError: If the vectors differ in length or are empty.
        """

        if len(vec1) != len(vec2):
            raise EmbeddingsServiceError(
                f"Vector length mismatch: {len(vec1)} != {len(vec2)}"
            )
        if not vec1:
            raise EmbeddingsServiceError("Vectors must be non-empty")
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot / (norm1 * norm2)


# Module-level singleton and functional wrappers.
_default_service: Optional[EmbeddingsService] = None


def get_service() -> EmbeddingsService:
    """Return a lazily-instantiated shared :class:`EmbeddingsService`."""

    global _default_service
    if _default_service is None:
        _default_service = EmbeddingsService()
    return _default_service


def generate_embedding(text: str) -> list[float]:
    """Module-level wrapper around :meth:`EmbeddingsService.generate_embedding`."""

    return get_service().generate_embedding(text)


def batch_generate_embeddings(texts: Sequence[str]) -> list[list[float]]:
    """Module-level wrapper around :meth:`EmbeddingsService.batch_generate_embeddings`."""

    return get_service().batch_generate_embeddings(texts)


def cosine_similarity(vec1: Sequence[float], vec2: Sequence[float]) -> float:
    """Module-level wrapper around :meth:`EmbeddingsService.cosine_similarity`."""

    return EmbeddingsService.cosine_similarity(vec1, vec2)


__all__ = [
    "EmbeddingsService",
    "EmbeddingsServiceError",
    "get_service",
    "generate_embedding",
    "batch_generate_embeddings",
    "cosine_similarity",
]
