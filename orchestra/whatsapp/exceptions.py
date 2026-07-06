"""WhatsApp-specific exceptions for the ORCHESTRA integration layer.

These wrap failures that are specific to the WhatsApp / WATI integration in a
small, stable hierarchy so callers (the sender, webhook, handlers, middleware)
can react without importing transport internals. Every exception raised by the
``orchestra.whatsapp`` package derives from :class:`WhatsAppError`.
"""

from __future__ import annotations

from typing import Optional


class WhatsAppError(Exception):
    """Base class for every error raised by the WhatsApp integration.

    Args:
        message: Human-readable description of what went wrong.
        original: The underlying exception that triggered this error, if any.
    """

    def __init__(self, message: str, *, original: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.message = message
        self.original = original

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.original is not None:
            return (
                f"{self.message} "
                f"(caused by {type(self.original).__name__}: {self.original})"
            )
        return self.message


class WhatsAppAPIError(WhatsAppError):
    """Raised when a WATI API call fails after all retries.

    Args:
        message: What failed.
        status_code: The HTTP status code returned by WATI, if any.
        payload: The decoded response body, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        payload: object = None,
        original: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message, original=original)
        self.status_code = status_code
        self.payload = payload


class WebhookValidationError(WhatsAppError):
    """Raised when an incoming webhook fails signature / payload validation."""


class RateLimitError(WhatsAppError):
    """Raised when a send would exceed the configured rate limit.

    Args:
        scope: What was rate-limited (e.g. ``"group"`` or ``"user"``).
        identifier: The group / user that hit the limit.
        retry_after: Seconds the caller should wait before retrying.
    """

    def __init__(
        self,
        message: str,
        *,
        scope: Optional[str] = None,
        identifier: Optional[str] = None,
        retry_after: Optional[float] = None,
        original: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message, original=original)
        self.scope = scope
        self.identifier = identifier
        self.retry_after = retry_after


class MediaDownloadError(WhatsAppError):
    """Raised when a media attachment cannot be downloaded."""

    def __init__(
        self,
        message: str,
        *,
        media_url: Optional[str] = None,
        original: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message, original=original)
        self.media_url = media_url


class GroupNotFoundError(WhatsAppError):
    """Raised when a referenced WhatsApp group is unknown / not registered."""

    def __init__(
        self,
        group_id: object = None,
        *,
        original: Optional[BaseException] = None,
    ) -> None:
        message = "WhatsApp group not found"
        if group_id is not None:
            message = f"WhatsApp group {group_id!r} not found"
        super().__init__(message, original=original)
        self.group_id = group_id


class SessionNotFoundError(WhatsAppError):
    """Raised when no active session exists for a group."""

    def __init__(
        self,
        group_id: object = None,
        *,
        original: Optional[BaseException] = None,
    ) -> None:
        message = "WhatsApp session not found"
        if group_id is not None:
            message = f"WhatsApp session for group {group_id!r} not found"
        super().__init__(message, original=original)
        self.group_id = group_id


class TemplateNotFoundError(WhatsAppError):
    """Raised when a named message template does not exist."""

    def __init__(
        self,
        name: object = None,
        *,
        original: Optional[BaseException] = None,
    ) -> None:
        message = "WhatsApp template not found"
        if name is not None:
            message = f"WhatsApp template {name!r} not found"
        super().__init__(message, original=original)
        self.name = name


__all__ = [
    "WhatsAppError",
    "WhatsAppAPIError",
    "WebhookValidationError",
    "RateLimitError",
    "MediaDownloadError",
    "GroupNotFoundError",
    "SessionNotFoundError",
    "TemplateNotFoundError",
]
