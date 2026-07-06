"""Per-message-type handlers that pre-process WhatsApp content.

Incoming WhatsApp messages arrive in many shapes — plain text, voice notes,
images, documents, locations, contacts and reactions. These handlers normalise
each type into a plain-text string that the
:class:`~orchestra.engine.orchestrator.Orchestrator` can understand, doing any
required pre-processing first:

* **voice** → transcribed with the self-hosted Whisper service,
* **image** → OCR'd (Tesseract, Arabic + English) with an optional caption,
* **document** → text extracted from PDF / DOCX where possible,
* **location / contact / reaction** → summarised into a short natural sentence.

Every heavy dependency (Whisper, OCR, PDF/DOCX parsers) is imported lazily and
failures degrade gracefully to a human-readable placeholder so a single bad
attachment never breaks the pipeline. Each handler forwards the normalised text
to :meth:`Orchestrator.handle_incoming_message` and returns its response.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Mapping, Optional

from .client import WATIClient
from .config import get_logger
from .exceptions import MediaDownloadError

_log = get_logger(__name__)


class MessageHandlers:
    """Async handlers that pre-process content then route to the orchestrator."""

    def __init__(
        self,
        *,
        orchestrator: Any = None,
        client: Optional[WATIClient] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._client = client

    # -- lazy dependency accessors -----------------------------------------
    @property
    def orchestrator(self) -> Any:
        if self._orchestrator is None:
            from ..engine import get_orchestrator

            self._orchestrator = get_orchestrator()
        return self._orchestrator

    @property
    def client(self) -> WATIClient:
        if self._client is None:
            self._client = WATIClient()
        return self._client

    # -- routing ------------------------------------------------------------
    async def _route(self, text: str, sender: str, group_id: str) -> dict[str, Any]:
        """Forward normalised ``text`` to the orchestrator."""

        return await self.orchestrator.handle_incoming_message(
            message=text, sender=sender, group_id=group_id
        )

    # -- text ---------------------------------------------------------------
    async def handle_text(
        self, message: Any, sender: str, group_id: str
    ) -> dict[str, Any]:
        """Handle a plain-text message."""

        text = _extract_text(message)
        return await self._route(text, sender, group_id)

    # -- voice --------------------------------------------------------------
    async def handle_voice(
        self, message: Any, sender: str, group_id: str
    ) -> dict[str, Any]:
        """Transcribe a voice note (Whisper) then route the text."""

        media_url = _media_url(message)
        transcript = ""
        if media_url:
            try:
                audio = await self.client.download_media(media_url)
                transcript = await self._transcribe(audio)
            except MediaDownloadError as exc:
                _log.error("Voice download failed: %s", exc)
            except Exception as exc:  # noqa: BLE001 - transcription is best effort
                _log.error("Voice transcription failed: %s", exc)
        text = transcript or "[voice message — could not transcribe]"
        return await self._route(text, sender, group_id)

    async def _transcribe(self, audio: bytes) -> str:
        """Transcribe audio bytes using the self-hosted Whisper service."""

        import asyncio

        def _run() -> str:
            from ..services.whisper_service import get_service  # lazy

            service = get_service()
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as fh:
                fh.write(audio)
                path = fh.name
            try:
                result = service.transcribe(path)
                if isinstance(result, dict):
                    return str(result.get("text", "")).strip()
                return str(result).strip()
            finally:
                _safe_unlink(path)

        return await asyncio.to_thread(_run)

    # -- image --------------------------------------------------------------
    async def handle_image(
        self, message: Any, sender: str, group_id: str
    ) -> dict[str, Any]:
        """OCR an image (Arabic + English) and combine with any caption."""

        caption = _caption(message)
        media_url = _media_url(message)
        ocr_text = ""
        if media_url:
            try:
                data = await self.client.download_media(media_url)
                ocr_text = await self._ocr(data)
            except MediaDownloadError as exc:
                _log.error("Image download failed: %s", exc)
            except Exception as exc:  # noqa: BLE001 - OCR is best effort
                _log.error("Image OCR failed: %s", exc)
        parts = [p for p in (caption, ocr_text) if p]
        text = "\n".join(parts) or "[image received]"
        return await self._route(text, sender, group_id)

    async def _ocr(self, image_bytes: bytes) -> str:
        """Run OCR over image bytes (Tesseract, ara+eng)."""

        import asyncio

        def _run() -> str:
            import io

            import pytesseract  # lazy — optional dependency
            from PIL import Image

            image = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(image, lang="ara+eng").strip()

        return await asyncio.to_thread(_run)

    # -- document -----------------------------------------------------------
    async def handle_document(
        self, message: Any, sender: str, group_id: str
    ) -> dict[str, Any]:
        """Extract text from a PDF / DOCX document and route it."""

        caption = _caption(message)
        filename = _filename(message)
        media_url = _media_url(message)
        extracted = ""
        if media_url:
            try:
                data = await self.client.download_media(media_url)
                extracted = await self._extract_document(data, filename)
            except MediaDownloadError as exc:
                _log.error("Document download failed: %s", exc)
            except Exception as exc:  # noqa: BLE001 - extraction is best effort
                _log.error("Document extraction failed: %s", exc)
        header = f"[document: {filename}]" if filename else "[document received]"
        parts = [p for p in (caption, extracted) if p]
        text = "\n".join([header, *parts]) if parts else header
        return await self._route(text, sender, group_id)

    async def _extract_document(self, data: bytes, filename: Optional[str]) -> str:
        import asyncio

        def _run() -> str:
            name = (filename or "").lower()
            if name.endswith(".pdf"):
                return _extract_pdf(data)
            if name.endswith(".docx"):
                return _extract_docx(data)
            # Unknown type: try to decode as UTF-8 text.
            try:
                return data.decode("utf-8", errors="ignore").strip()
            except Exception:  # noqa: BLE001 - binary blob
                return ""

        return await asyncio.to_thread(_run)

    # -- location -----------------------------------------------------------
    async def handle_location(
        self, message: Any, sender: str, group_id: str
    ) -> dict[str, Any]:
        """Summarise a shared location into a natural sentence."""

        lat = _get(message, "latitude", "lat")
        lng = _get(message, "longitude", "lng", "lon")
        name = _get(message, "name", "label", "address")
        pieces = []
        if name:
            pieces.append(str(name))
        if lat is not None and lng is not None:
            pieces.append(f"({lat}, {lng})")
        location = " ".join(pieces) if pieces else "an unspecified location"
        text = f"[location shared] {location}"
        return await self._route(text, sender, group_id)

    # -- contact ------------------------------------------------------------
    async def handle_contact(
        self, message: Any, sender: str, group_id: str
    ) -> dict[str, Any]:
        """Summarise a shared contact card."""

        name = _get(message, "name", "displayName", "formattedName")
        phone = _get(message, "phone", "phoneNumber", "waId", "number")
        parts = [str(p) for p in (name, phone) if p]
        detail = " — ".join(parts) if parts else "a contact"
        text = f"[contact shared] {detail}"
        return await self._route(text, sender, group_id)

    # -- reaction -----------------------------------------------------------
    async def handle_reaction(
        self, message: Any, sender: str, group_id: str
    ) -> dict[str, Any]:
        """Summarise an emoji reaction to a previous message."""

        emoji = _get(message, "emoji", "reaction", "text") or "👍"
        target = _get(message, "messageId", "targetId", "reactedTo")
        suffix = f" to message {target}" if target else ""
        text = f"[reaction {emoji}]{suffix}"
        return await self._route(text, sender, group_id)


# ---------------------------------------------------------------------------
# Extraction helpers (module-level, importable + testable)
# ---------------------------------------------------------------------------
def _extract_pdf(data: bytes) -> str:
    import io

    from pypdf import PdfReader  # lazy — optional dependency

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _extract_docx(data: bytes) -> str:
    import io

    import docx  # lazy — optional dependency (python-docx)

    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs).strip()


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:  # pragma: no cover - defensive
        pass


# ---------------------------------------------------------------------------
# Small payload accessors — tolerant of dict or object shapes
# ---------------------------------------------------------------------------
def _extract_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, Mapping):
        for key in ("text", "body", "message", "caption"):
            value = message.get(key)
            if value:
                return str(value)
    return str(message or "")


def _media_url(message: Any) -> Optional[str]:
    if isinstance(message, Mapping):
        for key in ("media_url", "mediaUrl", "url", "data", "fileUrl"):
            value = message.get(key)
            if value:
                return str(value)
    return None


def _caption(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("caption") or message.get("text") or "")
    return ""


def _filename(message: Any) -> Optional[str]:
    if isinstance(message, Mapping):
        return message.get("filename") or message.get("fileName") or message.get("name")
    return None


def _get(message: Any, *keys: str) -> Any:
    if isinstance(message, Mapping):
        for key in keys:
            if key in message and message[key] not in (None, ""):
                return message[key]
    else:
        for key in keys:
            value = getattr(message, key, None)
            if value not in (None, ""):
                return value
    return None


__all__ = ["MessageHandlers"]
