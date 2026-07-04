"""Sentiment service — Arabic emotion/urgency detection via a local model.

Loads a locally downloaded Arabic sentiment model (``./models/arabic-sentiment``
by default) with HuggingFace ``transformers`` and classifies text as
positive / negative / neutral with a confidence score. Useful for detecting
frustration or urgency in incoming messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Sequence

from .config import config, get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from transformers import Pipeline

_log = get_logger(__name__)

# Map common raw model labels onto a normalised vocabulary.
_LABEL_MAP = {
    "positive": "positive",
    "pos": "positive",
    "label_2": "positive",
    "negative": "negative",
    "neg": "negative",
    "label_0": "negative",
    "neutral": "neutral",
    "neu": "neutral",
    "label_1": "neutral",
}


class SentimentServiceError(RuntimeError):
    """Raised when sentiment analysis fails."""


class SentimentService:
    """Classify sentiment of Arabic (and English) text with a local model."""

    def __init__(self, model_path: Optional[str] = None, device: Optional[str] = None) -> None:
        self.model_path = model_path or config.sentiment_model
        self.device = device or config.torch_device
        self._pipeline: Optional["Pipeline"] = None

    # -- model loading ------------------------------------------------------
    @property
    def pipeline(self) -> "Pipeline":
        """Lazily build and cache the transformers text-classification pipeline."""

        if self._pipeline is None:
            try:
                from transformers import pipeline
            except ImportError as exc:  # pragma: no cover
                raise SentimentServiceError(
                    "transformers is not installed; see requirements.txt"
                ) from exc
            resolved = config.resolve_model_path(self.model_path)
            device_id = 0 if self.device == "cuda" else -1
            _log.info("Loading sentiment model %s (device=%s)", resolved, self.device)
            try:
                self._pipeline = pipeline(
                    "sentiment-analysis",
                    model=resolved,
                    tokenizer=resolved,
                    device=device_id,
                    truncation=True,
                )
            except Exception as exc:  # noqa: BLE001
                raise SentimentServiceError(
                    f"Failed to load sentiment model {resolved!r}: {exc}"
                ) from exc
        return self._pipeline

    # -- public API ---------------------------------------------------------
    def analyze(self, text: str) -> dict[str, Any]:
        """Return ``{"sentiment": str, "score": float, "raw_label": str}``."""

        if not isinstance(text, str) or not text.strip():
            raise SentimentServiceError("text must be a non-empty string")
        return self.analyze_batch([text])[0]

    def analyze_batch(self, texts: Sequence[str]) -> list[dict[str, Any]]:
        """Classify multiple texts, returning one result dict per input."""

        if not texts:
            return []
        cleaned = [t if isinstance(t, str) else str(t) for t in texts]
        try:
            predictions = self.pipeline(cleaned)
        except Exception as exc:  # noqa: BLE001
            raise SentimentServiceError(f"Sentiment analysis failed: {exc}") from exc
        if isinstance(predictions, dict):  # single-item safety
            predictions = [predictions]
        return [self._normalise(pred) for pred in predictions]

    @staticmethod
    def _normalise(pred: dict[str, Any]) -> dict[str, Any]:
        raw_label = str(pred.get("label", "")).strip()
        sentiment = _LABEL_MAP.get(raw_label.lower(), "neutral")
        return {
            "sentiment": sentiment,
            "score": float(pred.get("score", 0.0)),
            "raw_label": raw_label,
        }


# Module-level singleton and functional wrappers.
_default_service: Optional[SentimentService] = None


def get_service() -> SentimentService:
    """Return a lazily-instantiated shared :class:`SentimentService`."""

    global _default_service
    if _default_service is None:
        _default_service = SentimentService()
    return _default_service


def analyze(text: str) -> dict[str, Any]:
    """Module-level wrapper around :meth:`SentimentService.analyze`."""

    return get_service().analyze(text)


def analyze_batch(texts: Sequence[str]) -> list[dict[str, Any]]:
    """Module-level wrapper around :meth:`SentimentService.analyze_batch`."""

    return get_service().analyze_batch(texts)


__all__ = [
    "SentimentService",
    "SentimentServiceError",
    "get_service",
    "analyze",
    "analyze_batch",
]
