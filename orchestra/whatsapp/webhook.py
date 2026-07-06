"""WATI webhook receiver.

This module receives WhatsApp events from WATI, validates them, and routes
incoming messages into the orchestration engine via
:class:`~orchestra.whatsapp.handlers.MessageHandlers`.

It is intentionally **framework-agnostic**: the core is a set of async
functions plus a :class:`WebhookReceiver` class. A tiny :func:`route_request`
dispatcher maps the two documented routes so the module can be mounted on any
web framework (FastAPI, Starlette, aiohttp, …) with a couple of lines:

* ``POST /webhook/wati``   → :meth:`WebhookReceiver.handle_event`
* ``GET  /webhook/health`` → :meth:`WebhookReceiver.health_check`

Signatures are validated with HMAC-SHA256 over the raw request body using the
configured :data:`config.webhook_secret`.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Mapping, Optional, Union

from .config import WhatsAppConfig, config as default_config, get_logger
from .exceptions import WebhookValidationError
from .handlers import MessageHandlers

_log = get_logger(__name__)

WEBHOOK_PATH = "/webhook/wati"
HEALTH_PATH = "/webhook/health"

#: Maps a WATI event/message ``type`` to the handler method name on
#: :class:`MessageHandlers`.
_TYPE_HANDLERS = {
    "text": "handle_text",
    "chat": "handle_text",
    "button": "handle_text",
    "interactive": "handle_text",
    "audio": "handle_voice",
    "voice": "handle_voice",
    "ptt": "handle_voice",
    "image": "handle_image",
    "video": "handle_image",
    "document": "handle_document",
    "location": "handle_location",
    "contact": "handle_contact",
    "contacts": "handle_contact",
    "reaction": "handle_reaction",
}


class WebhookReceiver:
    """Validate and route WATI webhook events."""

    def __init__(
        self,
        *,
        config: Optional[WhatsAppConfig] = None,
        handlers: Optional[MessageHandlers] = None,
    ) -> None:
        self.config = config or default_config
        self._handlers = handlers

    @property
    def handlers(self) -> MessageHandlers:
        if self._handlers is None:
            self._handlers = MessageHandlers()
        return self._handlers

    # -- signature ----------------------------------------------------------
    def verify_signature(
        self, payload: Union[bytes, str], signature: Optional[str]
    ) -> bool:
        """Validate an HMAC-SHA256 ``signature`` over the raw ``payload``.

        Returns True when the signature matches. When no secret is configured
        and :data:`config.webhook_allow_unsigned` is True, verification is
        skipped (returns True) to ease local development.

        Args:
            payload: The **raw** request body (bytes preferred).
            signature: The signature header value; an optional ``sha256=``
                prefix is accepted.
        """

        secret = self.config.webhook_secret
        if not secret:
            if self.config.webhook_allow_unsigned:
                _log.debug("Webhook secret not set; skipping signature check")
                return True
            _log.warning("Webhook secret not set and unsigned not allowed")
            return False
        if not signature:
            return False

        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        provided = signature.split("=", 1)[1] if "=" in signature else signature
        expected = hmac.new(
            secret.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, provided.strip())

    def _require_signature(
        self, payload: Union[bytes, str], signature: Optional[str]
    ) -> None:
        if not self.verify_signature(payload, signature):
            raise WebhookValidationError("Invalid webhook signature")

    # -- event dispatch -----------------------------------------------------
    async def handle_event(
        self,
        payload: Mapping[str, Any],
        *,
        raw_body: Union[bytes, str, None] = None,
        signature: Optional[str] = None,
    ) -> dict[str, Any]:
        """Validate then dispatch a decoded webhook ``payload``.

        Args:
            payload: The decoded JSON body.
            raw_body: The raw request body used for signature verification. When
                omitted, ``payload`` is assumed pre-verified by middleware.
            signature: The signature header value, if verifying here.
        """

        if raw_body is not None:
            self._require_signature(raw_body, signature)

        event = _event_kind(payload)
        if event == "status":
            return await self.handle_status_update(payload)
        if event == "media":
            return await self.handle_media_upload(payload)
        return await self.handle_incoming_message(payload)

    async def handle_incoming_message(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Parse an inbound message payload and route it to the orchestrator."""

        parsed = parse_message(payload)
        # Ignore messages the bot itself sent.
        if parsed.get("from_me"):
            return {"status": "ignored", "reason": "outbound echo"}

        group_id = parsed["group_id"]
        sender = parsed["sender"]
        msg_type = parsed["type"]
        if not group_id:
            _log.warning("Webhook message without a group_id; ignoring")
            return {"status": "ignored", "reason": "missing group_id"}

        handler_name = _TYPE_HANDLERS.get(msg_type, "handle_text")
        handler = getattr(self.handlers, handler_name)
        _log.info(
            "Routing %s message from %s in %s -> %s",
            msg_type, sender, group_id, handler_name,
        )
        response = await handler(parsed["content"], sender, group_id)
        return {"status": "ok", "type": msg_type, "response": response}

    async def handle_status_update(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Handle a delivery / read status update (sent, delivered, read…)."""

        status = payload.get("status") or payload.get("eventType") or "unknown"
        message_id = payload.get("id") or payload.get("messageId")
        _log.info("Status update: message=%s status=%s", message_id, status)
        return {"status": "ok", "message_id": message_id, "delivery_status": status}

    async def handle_media_upload(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Handle a media-received event (delegates to the typed handler)."""

        return await self.handle_incoming_message(payload)

    async def health_check(self) -> dict[str, Any]:
        """Return webhook health details (for ``GET /webhook/health``)."""

        return {
            "status": "healthy",
            "webhook_path": WEBHOOK_PATH,
            "configured": self.config.is_configured,
            "signature_verification": bool(self.config.webhook_secret),
        }

    # -- routing ------------------------------------------------------------
    async def route_request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[Mapping[str, Any]] = None,
        raw_body: Union[bytes, str, None] = None,
        signature: Optional[str] = None,
    ) -> tuple[int, dict[str, Any]]:
        """Minimal dispatcher mapping the two documented routes.

        Returns ``(status_code, response_body)``. This lets the module be
        mounted on any framework without importing one here.
        """

        method = method.upper()
        if method == "GET" and path.rstrip("/") == HEALTH_PATH:
            return 200, await self.health_check()
        if method == "POST" and path.rstrip("/") == WEBHOOK_PATH:
            if body is None:
                return 400, {"status": "error", "error": "missing body"}
            try:
                result = await self.handle_event(
                    body, raw_body=raw_body, signature=signature
                )
                return 200, result
            except WebhookValidationError as exc:
                _log.warning("Webhook validation failed: %s", exc)
                return 401, {"status": "error", "error": str(exc)}
            except Exception as exc:  # noqa: BLE001 - never leak a 500 stack
                _log.error("Webhook handling error: %s", exc)
                return 500, {"status": "error", "error": "internal error"}
        return 404, {"status": "error", "error": "not found"}


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------
def _event_kind(payload: Mapping[str, Any]) -> str:
    """Classify a payload as ``"status"``, ``"media"`` or ``"message"``."""

    event = str(
        payload.get("eventType") or payload.get("event") or ""
    ).lower()
    if "status" in event or payload.get("status") in {
        "sent", "delivered", "read", "failed",
    } and not payload.get("text"):
        return "status"
    msg_type = str(payload.get("type") or "").lower()
    if msg_type in {"image", "video", "audio", "voice", "ptt", "document"}:
        return "media"
    return "message"


def parse_message(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalise a raw WATI payload into a stable internal shape.

    Returns a dict with keys: ``group_id``, ``sender``, ``type``, ``content``
    (a dict passed to the typed handler), ``message_id`` and ``from_me``.
    """

    msg_type = str(payload.get("type") or "text").lower()
    group_id = (
        payload.get("group_id")
        or payload.get("groupId")
        or payload.get("waId")
        or payload.get("chatId")
        or payload.get("conversationId")
        or ""
    )
    sender = (
        payload.get("sender")
        or payload.get("senderName")
        or payload.get("author")
        or payload.get("waId")
        or ""
    )
    text = payload.get("text") or payload.get("body") or payload.get("message") or ""

    content: dict[str, Any] = {
        "text": text,
        "caption": payload.get("caption") or payload.get("text") or "",
        "media_url": (
            payload.get("data")
            or payload.get("mediaUrl")
            or payload.get("media_url")
            or payload.get("url")
        ),
        "filename": payload.get("filename") or payload.get("fileName"),
        # location
        "latitude": payload.get("latitude") or payload.get("lat"),
        "longitude": payload.get("longitude") or payload.get("lng"),
        "name": payload.get("name") or payload.get("address"),
        # contact
        "phone": payload.get("phone") or payload.get("phoneNumber"),
        # reaction
        "emoji": payload.get("emoji") or payload.get("reaction"),
        "messageId": payload.get("replyContextId") or payload.get("targetId"),
    }

    return {
        "group_id": str(group_id),
        "sender": str(sender),
        "type": msg_type,
        "content": content,
        "message_id": payload.get("id") or payload.get("messageId"),
        "from_me": bool(payload.get("fromMe") or payload.get("owner")),
    }


# ---------------------------------------------------------------------------
# Module-level convenience API (backed by a shared receiver)
# ---------------------------------------------------------------------------
_receiver: Optional[WebhookReceiver] = None


def get_receiver() -> WebhookReceiver:
    """Return the shared :class:`WebhookReceiver` singleton."""

    global _receiver
    if _receiver is None:
        _receiver = WebhookReceiver()
    return _receiver


def verify_signature(payload: Union[bytes, str], signature: Optional[str]) -> bool:
    """Module-level shortcut for :meth:`WebhookReceiver.verify_signature`."""

    return get_receiver().verify_signature(payload, signature)


async def handle_incoming_message(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Module-level shortcut for :meth:`WebhookReceiver.handle_incoming_message`."""

    return await get_receiver().handle_incoming_message(payload)


async def handle_status_update(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Module-level shortcut for :meth:`WebhookReceiver.handle_status_update`."""

    return await get_receiver().handle_status_update(payload)


async def handle_media_upload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Module-level shortcut for :meth:`WebhookReceiver.handle_media_upload`."""

    return await get_receiver().handle_media_upload(payload)


async def health_check() -> dict[str, Any]:
    """Module-level shortcut for :meth:`WebhookReceiver.health_check`."""

    return await get_receiver().health_check()


__all__ = [
    "WebhookReceiver",
    "get_receiver",
    "parse_message",
    "verify_signature",
    "handle_incoming_message",
    "handle_status_update",
    "handle_media_upload",
    "health_check",
    "WEBHOOK_PATH",
    "HEALTH_PATH",
]
