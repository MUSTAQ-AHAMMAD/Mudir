"""LLM service — the main AI brain, backed by a local Ollama server.

This is the primary orchestrator: it talks to the locally installed Llama 3 /
Phi-3 model through Ollama's HTTP API and exposes higher-level helpers for
intent understanding, workflow extraction, response generation and
summarisation. It optionally delegates emotion detection to
``sentiment_service`` when available.

No external AI APIs are used — everything runs against ``localhost:11434``.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import config, get_logger

_log = get_logger(__name__)


class LLMServiceError(RuntimeError):
    """Raised when the LLM cannot fulfil a request after all retries."""


class LLMService:
    """Client for a local Ollama LLM with retry logic and JSON helpers."""

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self.model = model or config.llm_model
        self.base_url = (base_url or config.ollama_base_url).rstrip("/")
        self.timeout = timeout or config.llm_timeout
        self.max_retries = max_retries if max_retries is not None else config.llm_max_retries
        self._session = self._build_session(self.max_retries)

    # -- session / transport ------------------------------------------------
    @staticmethod
    def _build_session(max_retries: int) -> requests.Session:
        """Build a pooled ``requests`` session with connection-level retries."""

        session = requests.Session()
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            backoff_factor=0.5,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def close(self) -> None:
        """Close the underlying HTTP session."""

        self._session.close()

    def __enter__(self) -> "LLMService":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- health -------------------------------------------------------------
    def health_check(self) -> bool:
        """Return ``True`` when the Ollama server responds to ``/api/tags``."""

        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=self.timeout)
            return resp.ok
        except requests.RequestException as exc:
            _log.warning("Ollama health check failed: %s", exc)
            return False

    # -- core generate ------------------------------------------------------
    def chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        *,
        temperature: float = 0.7,
        format_json: bool = False,
    ) -> str:
        """Send a chat request to the local LLM and return the reply text.

        Args:
            prompt: The user prompt.
            model: Override the default model for this call.
            system: Optional system prompt.
            temperature: Sampling temperature.
            format_json: When ``True``, ask Ollama to constrain output to JSON.

        Returns:
            The assistant's response content as a string.

        Raises:
            LLMServiceError: If the request fails after all retries.
        """

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if format_json:
            payload["format"] = "json"

        data = self._post("/api/chat", payload)
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMServiceError(f"Unexpected chat response shape: {data!r}") from exc

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST ``payload`` to ``path`` with application-level retry/backoff."""

        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                wait = 0.5 * (2 ** (attempt - 1))
                _log.warning(
                    "LLM request to %s failed (attempt %d/%d): %s",
                    path,
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries:
                    time.sleep(wait)
        raise LLMServiceError(
            f"LLM request to {path} failed after {self.max_retries} attempts"
        ) from last_exc

    # -- JSON helper --------------------------------------------------------
    def _chat_json(self, prompt: str, system: str, temperature: float = 0.2) -> dict[str, Any]:
        """Run a chat expecting a JSON object and parse it defensively."""

        raw = self.chat(prompt, system=system, temperature=temperature, format_json=True)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """Parse a JSON object from an LLM reply, tolerating extra prose."""

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        # Fall back to extracting the first {...} block.
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        _log.warning("Could not parse JSON from LLM reply: %r", raw[:200])
        return {}

    # -- high-level capabilities -------------------------------------------
    def understand_intent(self, message: str) -> dict[str, Any]:
        """Extract intent, entities and sentiment from a user message.

        Returns a structured dict:
            {
              "intent": str,
              "entities": {..},
              "sentiment": "positive"|"negative"|"neutral",
              "urgency": "low"|"medium"|"high",
              "language": "ar"|"en"|..,
              "confidence": float
            }
        """

        system = (
            "You are an intent-extraction engine for a project-coordination "
            "assistant that works in Arabic and English. Respond ONLY with a "
            "JSON object with keys: intent (short snake_case string), entities "
            "(object of extracted values such as task, person, deadline, "
            "project), sentiment (positive|negative|neutral), urgency "
            "(low|medium|high), language (ISO code), confidence (0-1 float). "
            "Do not add commentary."
        )
        result = self._chat_json(f"Message:\n{message}", system=system)
        # Normalise / guarantee the shape.
        result.setdefault("intent", "unknown")
        result.setdefault("entities", {})
        result.setdefault("sentiment", "neutral")
        result.setdefault("urgency", "low")
        result.setdefault("language", "unknown")
        result.setdefault("confidence", 0.0)
        return result

    def extract_workflow(self, conversation: str) -> dict[str, Any]:
        """Learn workflow stages dynamically from a conversation transcript.

        Returns a dict with a ``stages`` list, each stage having ``name``,
        ``description``, ``owner`` (optional) and ``depends_on`` (list).
        """

        system = (
            "You analyse a conversation and infer the underlying project "
            "workflow. Respond ONLY with a JSON object: {\"workflow_name\": "
            "str, \"stages\": [{\"name\": str, \"description\": str, \"owner\": "
            "str|null, \"depends_on\": [str]}]}. Order stages logically. Do not "
            "invent stages that are not implied by the conversation."
        )
        result = self._chat_json(
            f"Conversation:\n{conversation}", system=system, temperature=0.3
        )
        result.setdefault("workflow_name", "unnamed_workflow")
        result.setdefault("stages", [])
        return result

    def generate_response(self, context: str, project: Optional[dict[str, Any]] = None) -> str:
        """Generate a human-like, bilingual (Arabic-first) coordinator reply.

        Args:
            context: Free-form context (recent messages, task status, etc.).
            project: Optional project metadata included in the prompt.
        """

        project_blurb = ""
        if project:
            try:
                project_blurb = "\nProject:\n" + json.dumps(project, ensure_ascii=False)
            except (TypeError, ValueError):
                project_blurb = f"\nProject: {project}"

        system = (
            "You are Mudir, a warm but concise project coordinator. Reply in "
            "Arabic first, then a short English fallback on a new line. Be "
            "actionable and reference concrete tasks, owners and deadlines when "
            "available. Never expose internal reasoning."
        )
        return self.chat(f"{context}{project_blurb}", system=system, temperature=0.6)

    def summarize_conversation(self, messages: list[Any]) -> str:
        """Summarise recent messages into a short bilingual digest.

        Args:
            messages: A list of message strings or ``{"role", "content"}`` dicts.
        """

        transcript = self._render_messages(messages)
        system = (
            "Summarise the following conversation for a busy manager. Provide a "
            "brief Arabic summary followed by an English one. Highlight "
            "decisions, blockers, and next actions as short bullet points."
        )
        return self.chat(f"Conversation:\n{transcript}", system=system, temperature=0.3)

    @staticmethod
    def _render_messages(messages: list[Any]) -> str:
        """Render a heterogeneous message list into plain transcript text."""

        lines: list[str] = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                lines.append(f"{role}: {content}")
            else:
                lines.append(str(msg))
        return "\n".join(lines)


# Convenience module-level singleton and functional wrappers.
_default_service: Optional[LLMService] = None


def get_service() -> LLMService:
    """Return a lazily-instantiated shared :class:`LLMService`."""

    global _default_service
    if _default_service is None:
        _default_service = LLMService()
    return _default_service


def chat(prompt: str, model: Optional[str] = None) -> str:
    """Module-level convenience wrapper around :meth:`LLMService.chat`."""

    return get_service().chat(prompt, model=model)


def understand_intent(message: str) -> dict[str, Any]:
    """Module-level wrapper around :meth:`LLMService.understand_intent`."""

    return get_service().understand_intent(message)


def extract_workflow(conversation: str) -> dict[str, Any]:
    """Module-level wrapper around :meth:`LLMService.extract_workflow`."""

    return get_service().extract_workflow(conversation)


def generate_response(context: str, project: Optional[dict[str, Any]] = None) -> str:
    """Module-level wrapper around :meth:`LLMService.generate_response`."""

    return get_service().generate_response(context, project)


def summarize_conversation(messages: list[Any]) -> str:
    """Module-level wrapper around :meth:`LLMService.summarize_conversation`."""

    return get_service().summarize_conversation(messages)


__all__ = [
    "LLMService",
    "LLMServiceError",
    "get_service",
    "chat",
    "understand_intent",
    "extract_workflow",
    "generate_response",
    "summarize_conversation",
]
