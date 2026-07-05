"""Intent detection and routing.

:class:`IntentRouter` is the natural-language front door of the engine. It uses
the local LLM (:mod:`orchestra.services.llm_service`) to classify a message into
one of a small set of canonical intents and to extract entities, and the
sentiment service (:mod:`orchestra.services.sentiment_service`) to gauge
frustration. It then maps the intent to an orchestrator command
(the *Command Pattern* seam) so the orchestrator can dispatch without a large
``if/elif`` ladder.

All network-bound methods are async; lightweight heuristics augment the model
output so the router still behaves sensibly if the LLM returns something vague.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..services.config import get_logger

_log = get_logger(__name__)

# Canonical intents and the orchestrator handler each maps to.
INTENT_HANDLERS: dict[str, str] = {
    "create_project": "create_new_project",
    "stage_complete": "handle_stage_completion",
    "task_complete": "handle_task_completion",
    "delay": "handle_delay",
    "escalation": "handle_escalation",
    "status": "get_project_status",
    "add_task": "add_task",
    "natural_language": "handle_natural_language",
}

# Keyword hints (English + common Arabic terms) used to canonicalise / augment
# whatever free-form intent the LLM returns.
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "create_project": ("open", "launch", "start", "new store", "new project", "افتتاح", "مشروع"),
    "stage_complete": ("stage done", "finished stage", "completed stage", "أنهينا المرحلة"),
    "task_complete": ("done", "completed", "finished", "خلصت", "تم"),
    "delay": ("delay", "late", "postpone", "extension", "تأخير", "تأجيل"),
    "escalation": ("urgent", "escalate", "problem", "blocked", "مشكلة", "عاجل"),
    "status": ("status", "progress", "update", "where are we", "الوضع", "التقدم"),
    "add_task": ("add task", "new task", "please do", "assign", "مهمة"),
}

_URGENCY_KEYWORDS = (
    "urgent", "asap", "immediately", "now", "critical", "emergency",
    "عاجل", "فورا", "حالا", "طارئ",
)
_CONFUSION_KEYWORDS = (
    "confused", "don't understand", "dont understand", "what do you mean",
    "how do i", "not sure", "لم أفهم", "كيف", "ماذا تقصد",
)
_FRUSTRATION_KEYWORDS = (
    "frustrated", "angry", "unacceptable", "ridiculous", "again?!", "fed up",
    "غاضب", "غير مقبول", "زهقت",
)

_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|"
    r"tomorrow|today|next week|next month)\b",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"\+?\d[\d\s\-]{6,}\d")


class IntentRouter:
    """Classify messages, extract entities and route to command handlers."""

    def __init__(
        self,
        llm_service: Any = None,
        sentiment_service: Any = None,
    ) -> None:
        self._llm = llm_service
        self._sentiment = sentiment_service

    # -- lazy dependency accessors -----------------------------------------
    @property
    def llm(self) -> Any:
        if self._llm is None:
            from ..services import llm_service

            self._llm = llm_service.get_service()
        return self._llm

    @property
    def sentiment(self) -> Any:
        if self._sentiment is None:
            from ..services import sentiment_service

            self._sentiment = sentiment_service.get_service()
        return self._sentiment

    # -- classification -----------------------------------------------------
    async def classify_intent(self, message: str) -> dict[str, Any]:
        """Classify ``message`` into a canonical intent.

        Returns:
            ``{"intent": str, "confidence": float, "raw_intent": str,
            "understanding": {..}}`` where ``intent`` is one of
            :data:`INTENT_HANDLERS`.
        """

        understanding = self.llm.understand_intent(message)
        raw_intent = str(understanding.get("intent", "unknown"))
        confidence = float(understanding.get("confidence", 0.0) or 0.0)
        canonical = self._canonicalise(raw_intent, message)
        return {
            "intent": canonical,
            "confidence": confidence,
            "raw_intent": raw_intent,
            "understanding": understanding,
        }

    def _canonicalise(self, raw_intent: str, message: str) -> str:
        """Map a raw/free-form intent to a canonical one via hints."""

        raw = raw_intent.lower()
        for canonical in INTENT_HANDLERS:
            if canonical in raw:
                return canonical
        haystack = f"{raw} {message.lower()}"
        for canonical, keywords in _INTENT_KEYWORDS.items():
            if any(kw in haystack for kw in keywords):
                return canonical
        return "natural_language"

    async def extract_entities(self, message: str) -> dict[str, Any]:
        """Extract key entities (dates, people, locations, phone numbers).

        Combines the LLM's structured entities with regex-based extraction so
        obvious dates and phone numbers are never missed.
        """

        understanding = self.llm.understand_intent(message)
        entities = dict(understanding.get("entities") or {})
        dates = _DATE_RE.findall(message)
        if dates and not entities.get("dates"):
            entities["dates"] = dates
        phones = _PHONE_RE.findall(message)
        if phones and not entities.get("phones"):
            entities["phones"] = [p.strip() for p in phones]
        return entities

    # -- signal detectors ---------------------------------------------------
    async def detect_urgency(self, message: str) -> dict[str, Any]:
        """Return an urgency assessment for ``message``."""

        lowered = message.lower()
        keyword_hit = any(kw in lowered for kw in _URGENCY_KEYWORDS)
        try:
            understanding = self.llm.understand_intent(message)
            level = str(understanding.get("urgency", "low")).lower()
        except Exception as exc:  # noqa: BLE001 - LLM optional here
            _log.debug("Urgency LLM check failed: %s", exc)
            level = "high" if keyword_hit else "low"
        if keyword_hit and level == "low":
            level = "high"
        return {"urgent": level in {"high", "medium"} or keyword_hit, "level": level}

    async def detect_confusion(self, message: str) -> bool:
        """Return ``True`` when the user appears confused."""

        lowered = message.lower()
        if any(kw in lowered for kw in _CONFUSION_KEYWORDS):
            return True
        # A short message ending in a question mark is a weak confusion signal.
        return message.strip().endswith("?") and len(message.split()) <= 6

    async def detect_frustration(self, message: str) -> dict[str, Any]:
        """Return a frustration assessment using sentiment + keywords."""

        lowered = message.lower()
        keyword_hit = any(kw in lowered for kw in _FRUSTRATION_KEYWORDS)
        label, score = "neutral", 0.0
        try:
            result = self.sentiment.analyze(message)
            label = str(result.get("label", "neutral")).lower()
            score = float(result.get("score", 0.0) or 0.0)
        except Exception as exc:  # noqa: BLE001 - sentiment optional
            _log.debug("Sentiment analysis failed: %s", exc)
        frustrated = keyword_hit or (
            label in {"negative", "anger", "angry"} and score >= 0.6
        )
        return {"frustrated": frustrated, "label": label, "score": score}

    # -- routing ------------------------------------------------------------
    def route_intent(
        self,
        intent: str,
        entities: Optional[dict[str, Any]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Map an intent to an orchestrator command descriptor.

        Returns:
            ``{"command": str, "handler": str, "entities": {..},
            "context": {..}}``. ``handler`` is the name of the orchestrator
            coroutine to invoke.
        """

        canonical = intent if intent in INTENT_HANDLERS else "natural_language"
        return {
            "command": canonical,
            "handler": INTENT_HANDLERS[canonical],
            "entities": entities or {},
            "context": context or {},
        }

    async def fallback_llm_response(
        self, message: str, context: Optional[dict[str, Any]] = None
    ) -> str:
        """Generate a free-form reply when no structured intent applies."""

        context_blurb = ""
        if context:
            import json

            try:
                context_blurb = "\nContext:\n" + json.dumps(context, ensure_ascii=False)
            except (TypeError, ValueError):
                context_blurb = f"\nContext: {context}"
        return self.llm.generate_response(f"{message}{context_blurb}")


__all__ = ["IntentRouter", "INTENT_HANDLERS"]
