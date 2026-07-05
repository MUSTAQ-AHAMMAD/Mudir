"""Webhook middleware: rate limiting, auth, logging, error handling, timeouts.

These are small, framework-agnostic building blocks that operate on a
:class:`WebhookRequest` value object. Each middleware is an async callable that
either returns ``None`` (meaning *continue*) or a ``(status_code, body)`` tuple
that short-circuits the request. This mirrors the return shape of
:meth:`orchestra.whatsapp.webhook.WebhookReceiver.route_request` so the pieces
compose naturally.

Example wiring::

    stack = MiddlewareStack([
        LoggingMiddleware(),
        AuthMiddleware(),
        RateLimitMiddleware(),
        TimeoutMiddleware(),
    ])
    short_circuit = await stack.process(request)
    if short_circuit is not None:
        status, body = short_circuit
    else:
        status, body = await receiver.route_request(...)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Optional

from .client import SlidingWindowRateLimiter
from .config import WhatsAppConfig, config as default_config, get_logger
from .exceptions import RateLimitError
from .webhook import WebhookReceiver, parse_message

_log = get_logger(__name__)

#: A middleware returns None to continue, or a (status, body) tuple to stop.
Result = Optional[tuple[int, dict[str, Any]]]


@dataclass
class WebhookRequest:
    """A minimal, framework-agnostic view of an inbound webhook request."""

    method: str = "POST"
    path: str = "/webhook/wati"
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Optional[Mapping[str, Any]] = None
    raw_body: Any = None
    #: Populated lazily by middleware that need the parsed identifiers.
    group_id: Optional[str] = None
    user_id: Optional[str] = None

    def header(self, name: str) -> Optional[str]:
        """Case-insensitive header lookup."""

        lower = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lower:
                return value
        return None

    def ensure_parsed(self) -> None:
        """Fill ``group_id`` / ``user_id`` from the body if not already set."""

        if (self.group_id is None or self.user_id is None) and self.body:
            parsed = parse_message(self.body)
            if self.group_id is None:
                self.group_id = parsed.get("group_id") or None
            if self.user_id is None:
                self.user_id = parsed.get("sender") or None


# ---------------------------------------------------------------------------
# Individual middleware
# ---------------------------------------------------------------------------
class RateLimitMiddleware:
    """Rate-limit inbound webhooks per group and per user (sliding window)."""

    def __init__(
        self,
        *,
        config: Optional[WhatsAppConfig] = None,
        group_limiter: Optional[SlidingWindowRateLimiter] = None,
        user_limiter: Optional[SlidingWindowRateLimiter] = None,
    ) -> None:
        cfg = config or default_config
        self.group_limiter = group_limiter or SlidingWindowRateLimiter(
            cfg.rate_limit_per_group, cfg.rate_limit_window
        )
        self.user_limiter = user_limiter or SlidingWindowRateLimiter(
            cfg.rate_limit_per_user, cfg.rate_limit_window
        )

    async def __call__(self, request: WebhookRequest) -> Result:
        request.ensure_parsed()
        try:
            if request.group_id:
                await self.group_limiter.acquire(request.group_id)
            if request.user_id:
                await self.user_limiter.acquire(request.user_id)
        except RateLimitError as exc:
            _log.warning("Rate limit hit: %s", exc)
            return 429, {
                "status": "error",
                "error": "rate limited",
                "scope": exc.scope,
                "retry_after": exc.retry_after,
            }
        return None


# Backwards-friendly functional alias.
async def rate_limit_middleware(request: WebhookRequest) -> Result:
    """Function form of :class:`RateLimitMiddleware` using default config."""

    return await RateLimitMiddleware()(request)


class AuthMiddleware:
    """Validate the webhook HMAC-SHA256 signature."""

    def __init__(
        self,
        *,
        receiver: Optional[WebhookReceiver] = None,
        signature_header: str = "x-wati-signature",
    ) -> None:
        self.receiver = receiver or WebhookReceiver()
        self.signature_header = signature_header

    async def __call__(self, request: WebhookRequest) -> Result:
        # Only POST webhooks carry a signed body.
        if request.method.upper() != "POST":
            return None
        signature = request.header(self.signature_header) or request.header(
            "x-signature"
        )
        raw = request.raw_body
        if raw is None and request.body is not None:
            # Fall back to the decoded body if no raw bytes were captured.
            import json

            raw = json.dumps(request.body, separators=(",", ":"), ensure_ascii=False)
        if not self.receiver.verify_signature(raw or b"", signature):
            _log.warning("Rejected webhook with invalid signature")
            return 401, {"status": "error", "error": "invalid signature"}
        return None


async def auth_middleware(request: WebhookRequest) -> Result:
    """Function form of :class:`AuthMiddleware` using default config."""

    return await AuthMiddleware()(request)


class LoggingMiddleware:
    """Log every inbound request (method, path, group/user)."""

    async def __call__(self, request: WebhookRequest) -> Result:
        request.ensure_parsed()
        _log.info(
            "Webhook %s %s group=%s user=%s",
            request.method,
            request.path,
            request.group_id,
            request.user_id,
        )
        return None


async def logging_middleware(request: WebhookRequest) -> Result:
    """Function form of :class:`LoggingMiddleware`."""

    return await LoggingMiddleware()(request)


def error_middleware(error: BaseException) -> tuple[int, dict[str, Any]]:
    """Translate an exception into a safe ``(status, body)`` response.

    Never leaks internal details or stack traces to the caller.
    """

    from .exceptions import RateLimitError as _RLE
    from .exceptions import WebhookValidationError

    if isinstance(error, WebhookValidationError):
        return 401, {"status": "error", "error": str(error)}
    if isinstance(error, _RLE):
        return 429, {
            "status": "error",
            "error": "rate limited",
            "retry_after": getattr(error, "retry_after", None),
        }
    _log.error("Unhandled webhook error: %s", error)
    return 500, {"status": "error", "error": "internal error"}


class TimeoutMiddleware:
    """Enforce a timeout on the downstream handler coroutine."""

    def __init__(self, *, timeout: Optional[float] = None) -> None:
        self.timeout = timeout if timeout is not None else default_config.webhook_request_timeout

    async def run(
        self,
        handler: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Run ``handler`` under the configured timeout.

        Raises:
            asyncio.TimeoutError: If the handler exceeds the timeout.
        """

        return await asyncio.wait_for(handler(*args, **kwargs), timeout=self.timeout)

    async def __call__(self, request: WebhookRequest) -> Result:
        # As a pre-flight middleware it does not short-circuit; use :meth:`run`
        # to wrap the actual handler execution.
        return None


async def timeout_middleware(
    request: WebhookRequest,
    handler: Optional[Callable[..., Awaitable[Any]]] = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Function form: wrap ``handler`` under the default timeout.

    When called without a handler it is a no-op pre-flight middleware
    (returns ``None``); otherwise it runs and returns the handler result.
    """

    mw = TimeoutMiddleware()
    if handler is None:
        return None
    return await mw.run(handler, *args, **kwargs)


# ---------------------------------------------------------------------------
# Stack
# ---------------------------------------------------------------------------
class MiddlewareStack:
    """Run a list of pre-flight middleware in order, short-circuiting on stop."""

    def __init__(self, middleware: list[Callable[[WebhookRequest], Awaitable[Result]]]):
        self.middleware = list(middleware)

    async def process(self, request: WebhookRequest) -> Result:
        """Run each middleware; return the first short-circuit result or None."""

        start = time.monotonic()
        for mw in self.middleware:
            result = await mw(request)
            if result is not None:
                return result
        _log.debug(
            "Middleware stack passed in %.1fms",
            (time.monotonic() - start) * 1000,
        )
        return None


def default_stack() -> MiddlewareStack:
    """Return the recommended middleware order for production use."""

    return MiddlewareStack(
        [
            LoggingMiddleware(),
            AuthMiddleware(),
            RateLimitMiddleware(),
        ]
    )


__all__ = [
    "WebhookRequest",
    "RateLimitMiddleware",
    "AuthMiddleware",
    "LoggingMiddleware",
    "TimeoutMiddleware",
    "MiddlewareStack",
    "default_stack",
    "rate_limit_middleware",
    "auth_middleware",
    "logging_middleware",
    "error_middleware",
    "timeout_middleware",
]
