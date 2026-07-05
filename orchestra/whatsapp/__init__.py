"""ORCHESTRA WhatsApp integration layer (Phase 4).

This package connects the orchestration engine (:mod:`orchestra.engine`) to
WhatsApp Groups through the `WATI <https://www.wati.io>`_ API. It provides the
outbound transport (:class:`WhatsAppSender`, which implements the engine's
``WhatsAppSender`` protocol), an inbound webhook receiver, message handlers,
bilingual templates, session management and webhook middleware.

Quick start::

    from orchestra.engine import get_orchestrator
    from orchestra.whatsapp import WhatsAppSender, WhatsAppClient

    # Wire the transport into the engine.
    orchestrator = get_orchestrator(whatsapp_service=WhatsAppSender())

    # Send a message.
    client = WhatsAppClient()
    await client.send_message("group123", "Test message")

    # Render a bilingual template.
    from orchestra.whatsapp import templates
    text = templates.render("PROJECT_CREATED",
                            {"project_name": "Riyadh Mall", "team": "Property"},
                            lang="ar")

Heavy dependencies (``httpx``, Whisper, OCR, PDF/DOCX parsers) are imported
lazily so importing this package stays cheap and side-effect free.
"""

from __future__ import annotations

from . import templates
from .client import SlidingWindowRateLimiter, WATIClient, WhatsAppClient
from .config import WhatsAppConfig, config, get_logger, reload_config
from .exceptions import (
    GroupNotFoundError,
    MediaDownloadError,
    RateLimitError,
    SessionNotFoundError,
    TemplateNotFoundError,
    WebhookValidationError,
    WhatsAppAPIError,
    WhatsAppError,
)
from .handlers import MessageHandlers
from .middleware import (
    AuthMiddleware,
    LoggingMiddleware,
    MiddlewareStack,
    RateLimitMiddleware,
    TimeoutMiddleware,
    WebhookRequest,
    default_stack,
)
from .sender import WhatsAppSender
from .session_manager import SessionManager
from .webhook import WebhookReceiver, get_receiver

__all__ = [
    # config
    "WhatsAppConfig",
    "config",
    "reload_config",
    "get_logger",
    # client
    "WATIClient",
    "WhatsAppClient",
    "SlidingWindowRateLimiter",
    # sender (implements the engine WhatsAppSender protocol)
    "WhatsAppSender",
    # webhook + handlers
    "WebhookReceiver",
    "get_receiver",
    "MessageHandlers",
    # sessions
    "SessionManager",
    # middleware
    "WebhookRequest",
    "MiddlewareStack",
    "default_stack",
    "AuthMiddleware",
    "RateLimitMiddleware",
    "LoggingMiddleware",
    "TimeoutMiddleware",
    # templates
    "templates",
    # exceptions
    "WhatsAppError",
    "WhatsAppAPIError",
    "WebhookValidationError",
    "RateLimitError",
    "MediaDownloadError",
    "GroupNotFoundError",
    "SessionNotFoundError",
    "TemplateNotFoundError",
]
