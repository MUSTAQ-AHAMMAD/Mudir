"""Translation service — Arabic ↔ English via NLLB-200 (optional).

Uses Meta's NLLB-200 distilled model through HuggingFace ``transformers`` for
offline translation. Language detection is heuristic (Arabic Unicode range) so
the module has no hard dependency on an external language-detection package.

This service is optional: importing it succeeds even when ``transformers`` is
absent — the dependency is only required when a translation is actually run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .config import config, get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from transformers import PreTrainedModel, PreTrainedTokenizerBase

_log = get_logger(__name__)

# Map short ISO codes to NLLB's FLORES-200 language codes.
_NLLB_LANG = {
    "ar": "arb_Arab",
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "ur": "urd_Arab",
    "hi": "hin_Deva",
}


class TranslationServiceError(RuntimeError):
    """Raised when translation fails."""


class TranslationService:
    """Translate text with a locally hosted NLLB-200 model."""

    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None) -> None:
        self.model_name = model_name or config.translation_model
        self.device = device or config.torch_device
        self._model: Optional["PreTrainedModel"] = None
        self._tokenizer: Optional["PreTrainedTokenizerBase"] = None

    # -- model loading ------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover
            raise TranslationServiceError(
                "transformers is not installed; see requirements.txt"
            ) from exc
        resolved = config.resolve_model_path(self.model_name)
        _log.info("Loading translation model %s (device=%s)", resolved, self.device)
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(resolved)
            model = AutoModelForSeq2SeqLM.from_pretrained(resolved)
            self._model = model.to(self.device)
        except Exception as exc:  # noqa: BLE001
            raise TranslationServiceError(
                f"Failed to load translation model {resolved!r}: {exc}"
            ) from exc

    # -- public API ---------------------------------------------------------
    def detect_language(self, text: str) -> str:
        """Heuristically detect the language, returning an ISO code.

        Currently distinguishes Arabic (``"ar"``) from other text (``"en"``)
        based on the proportion of Arabic-script characters.
        """

        if not text or not text.strip():
            return "unknown"
        arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06ff")
        letters = sum(1 for ch in text if ch.isalpha())
        if letters == 0:
            return "unknown"
        return "ar" if arabic / letters > 0.4 else "en"

    def translate(self, text: str, target_lang: str, source_lang: Optional[str] = None) -> str:
        """Translate ``text`` into ``target_lang`` (ISO code, e.g. ``"en"``).

        The source language is auto-detected when not provided.
        """

        if not text or not text.strip():
            return ""
        src = source_lang or self.detect_language(text)
        src_code = _NLLB_LANG.get(src)
        tgt_code = _NLLB_LANG.get(target_lang)
        if src_code is None or tgt_code is None:
            raise TranslationServiceError(
                f"Unsupported language pair {src!r} -> {target_lang!r}"
            )

        self._ensure_loaded()
        assert self._tokenizer is not None and self._model is not None
        try:
            self._tokenizer.src_lang = src_code
            encoded = self._tokenizer(text, return_tensors="pt", truncation=True)
            encoded = {k: v.to(self.device) for k, v in encoded.items()}
            bos = self._tokenizer.convert_tokens_to_ids(tgt_code)
            generated = self._model.generate(
                **encoded, forced_bos_token_id=bos, max_length=512
            )
            return self._tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
        except Exception as exc:  # noqa: BLE001
            raise TranslationServiceError(f"Translation failed: {exc}") from exc


# Module-level singleton and functional wrappers.
_default_service: Optional[TranslationService] = None


def get_service() -> TranslationService:
    """Return a lazily-instantiated shared :class:`TranslationService`."""

    global _default_service
    if _default_service is None:
        _default_service = TranslationService()
    return _default_service


def translate(text: str, target_lang: str) -> str:
    """Module-level wrapper around :meth:`TranslationService.translate`."""

    return get_service().translate(text, target_lang)


def detect_language(text: str) -> str:
    """Module-level wrapper around :meth:`TranslationService.detect_language`."""

    return get_service().detect_language(text)


__all__ = [
    "TranslationService",
    "TranslationServiceError",
    "get_service",
    "translate",
    "detect_language",
]
