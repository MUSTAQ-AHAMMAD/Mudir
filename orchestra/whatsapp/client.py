"""Async WATI API client for WhatsApp Groups.

:class:`WATIClient` (aliased as :class:`WhatsAppClient`) is a thin, resilient
wrapper over the `WATI <https://www.wati.io>`_ REST API. It provides:

* async methods for the operations the platform needs (send text / template,
  fetch group info & members, download media, mark-as-read, health check),
* **retry logic** with exponential backoff + jitter for transient failures,
* **per-group / per-user rate limiting** (sliding window),
* **connection pooling** via a shared :class:`httpx.AsyncClient`.

The HTTP layer is injectable: pass a ``transport`` coroutine to construct the
client without a network / ``httpx`` dependency (used by the unit tests). When
no transport is supplied, an :class:`httpx.AsyncClient` is created lazily on
first use so importing this module stays cheap and side-effect free.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from typing import Any, Awaitable, Callable, Mapping, Optional

from .config import WhatsAppConfig, config as default_config, get_logger
from .exceptions import (
    MediaDownloadError,
    RateLimitError,
    WhatsAppAPIError,
)

_log = get_logger(__name__)

#: Signature of an injectable async HTTP transport. It must return an object
#: exposing ``status_code`` (int), ``json()`` and ``content`` / ``text``.
Transport = Callable[..., Awaitable[Any]]

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
class SlidingWindowRateLimiter:
    """A simple async sliding-window rate limiter keyed by an identifier.

    Tracks the timestamps of recent events per key and allows at most
    ``max_events`` within ``window`` seconds. Thread-safe across coroutines via
    an :class:`asyncio.Lock`.
    """

    def __init__(self, max_events: int, window: float) -> None:
        self.max_events = max_events
        self.window = window
        self._events: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    def _now(self) -> float:
        return time.monotonic()

    async def check(self, key: str) -> tuple[bool, float]:
        """Return ``(allowed, retry_after)`` without recording an event."""

        async with self._lock:
            return self._check_locked(key)

    def _check_locked(self, key: str) -> tuple[bool, float]:
        now = self._now()
        bucket = self._events.setdefault(key, deque())
        while bucket and now - bucket[0] >= self.window:
            bucket.popleft()
        if len(bucket) >= self.max_events:
            retry_after = self.window - (now - bucket[0])
            return False, max(retry_after, 0.0)
        return True, 0.0

    async def acquire(self, key: str) -> None:
        """Record an event for ``key`` or raise :class:`RateLimitError`."""

        async with self._lock:
            allowed, retry_after = self._check_locked(key)
            if not allowed:
                raise RateLimitError(
                    f"Rate limit exceeded for {key!r}",
                    identifier=key,
                    retry_after=retry_after,
                )
            self._events[key].append(self._now())


# ---------------------------------------------------------------------------
# WATI client
# ---------------------------------------------------------------------------
class WATIClient:
    """Resilient async client for the WATI WhatsApp API."""

    def __init__(
        self,
        *,
        config: Optional[WhatsAppConfig] = None,
        transport: Optional[Transport] = None,
        group_rate_limiter: Optional[SlidingWindowRateLimiter] = None,
        user_rate_limiter: Optional[SlidingWindowRateLimiter] = None,
    ) -> None:
        self.config = config or default_config
        self._transport = transport
        self._client: Any = None  # lazily-created httpx.AsyncClient
        self._client_lock = asyncio.Lock()
        self.group_limiter = group_rate_limiter or SlidingWindowRateLimiter(
            self.config.rate_limit_per_group, self.config.rate_limit_window
        )
        self.user_limiter = user_rate_limiter or SlidingWindowRateLimiter(
            self.config.rate_limit_per_user, self.config.rate_limit_window
        )

    # -- transport / pooling ------------------------------------------------
    async def _get_client(self) -> Any:
        """Return (creating if needed) the pooled ``httpx.AsyncClient``."""

        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                import httpx  # lazy import — keeps package import cheap

                limits = httpx.Limits(
                    max_connections=self.config.pool_max_connections,
                    max_keepalive_connections=self.config.pool_max_keepalive,
                )
                self._client = httpx.AsyncClient(
                    base_url=self.config.base_url,
                    timeout=self.config.request_timeout,
                    limits=limits,
                    headers=self.config.auth_header,
                )
        return self._client

    async def _raw_request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Optional[Any] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        """Perform a single HTTP request via the injected or pooled transport."""

        if self._transport is not None:
            return await self._transport(
                method, url, params=params, json=json, headers=headers
            )
        client = await self._get_client()
        return await client.request(
            method, url, params=params, json=json, headers=headers
        )

    # -- retry --------------------------------------------------------------
    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter (seconds)."""

        base = self.config.retry_backoff_base * (2 ** attempt)
        capped = min(base, self.config.retry_backoff_max)
        return random.uniform(0, capped)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Optional[Any] = None,
        headers: Optional[Mapping[str, str]] = None,
        expect_json: bool = True,
    ) -> Any:
        """Perform a request with retry + exponential backoff.

        Retries on connection errors and on ``429`` / ``5xx`` responses up to
        :data:`config.max_retries` times.

        Raises:
            WhatsAppAPIError: If the request ultimately fails.
        """

        attempts = self.config.max_retries + 1
        last_exc: Optional[BaseException] = None
        for attempt in range(attempts):
            try:
                response = await self._raw_request(
                    method, url, params=params, json=json, headers=headers
                )
            except Exception as exc:  # noqa: BLE001 - normalise transport errors
                last_exc = exc
                _log.warning(
                    "WATI %s %s failed (attempt %d/%d): %s",
                    method, url, attempt + 1, attempts, exc,
                )
                if attempt + 1 >= attempts:
                    raise WhatsAppAPIError(
                        f"Request to {url} failed", original=exc
                    ) from exc
                await asyncio.sleep(self._backoff(attempt))
                continue

            status = getattr(response, "status_code", 200)
            if status in _RETRYABLE_STATUS and attempt + 1 < attempts:
                _log.warning(
                    "WATI %s %s returned %s; retrying (%d/%d)",
                    method, url, status, attempt + 1, attempts,
                )
                await asyncio.sleep(self._backoff(attempt))
                continue
            if status >= 400:
                body = _safe_body(response)
                raise WhatsAppAPIError(
                    f"WATI {method} {url} returned {status}",
                    status_code=status,
                    payload=body,
                )
            return _decode(response) if expect_json else response

        # Should be unreachable, but keep mypy / callers happy.
        raise WhatsAppAPIError(
            f"Request to {url} failed", original=last_exc
        )

    # -- public API ---------------------------------------------------------
    async def send_message(
        self,
        group_id: str,
        message: str,
        options: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Send a text ``message`` to a WhatsApp group / recipient.

        Args:
            group_id: The WATI whatsapp number / group identifier.
            message: The message text (Arabic or English).
            options: Optional extra fields merged into the request body.

        Raises:
            RateLimitError: If the per-group limit is exceeded.
            WhatsAppAPIError: If the API call fails.
        """

        await self.group_limiter.acquire(group_id)
        payload: dict[str, Any] = {"messageText": message}
        if options:
            payload.update(options)
        return await self._request(
            "POST",
            "/api/v1/sendSessionMessage/" + str(group_id),
            params={"whatsappNumber": group_id, "messageText": message},
            json=payload,
        )

    async def send_direct_message(
        self, phone_number: str, message: str
    ) -> dict[str, Any]:
        """Send a direct (1:1) text message to ``phone_number``."""

        await self.user_limiter.acquire(phone_number)
        return await self._request(
            "POST",
            "/api/v1/sendSessionMessage/" + str(phone_number),
            params={"whatsappNumber": phone_number, "messageText": message},
            json={"messageText": message},
        )

    async def send_template(
        self,
        group_id: str,
        template_name: str,
        variables: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Send a pre-approved Meta template message.

        Args:
            group_id: The recipient / group identifier.
            template_name: The WATI/Meta approved template name.
            variables: Mapping of placeholder name -> value.
        """

        await self.group_limiter.acquire(group_id)
        params: dict[str, Any] = {
            "whatsappNumber": group_id,
        }
        parameters = [
            {"name": str(k), "value": str(v)}
            for k, v in (variables or {}).items()
        ]
        body: dict[str, Any] = {
            "template_name": template_name,
            "broadcast_name": template_name,
            "parameters": parameters,
        }
        if self.config.template_namespace:
            body["namespace"] = self.config.template_namespace
        return await self._request(
            "POST",
            "/api/v1/sendTemplateMessage",
            params=params,
            json=body,
        )

    async def get_group_members(self, group_id: str) -> list[dict[str, Any]]:
        """Return the list of members for ``group_id``."""

        data = await self._request(
            "GET",
            "/api/v1/getGroupMembers",
            params={"groupId": group_id},
        )
        if isinstance(data, dict):
            members = data.get("members") or data.get("contacts") or []
            return list(members)
        return list(data) if isinstance(data, list) else []

    async def get_group_info(self, group_id: str) -> dict[str, Any]:
        """Return metadata about ``group_id``."""

        data = await self._request(
            "GET",
            "/api/v1/getGroupInfo",
            params={"groupId": group_id},
        )
        return data if isinstance(data, dict) else {"result": data}

    async def download_media(self, media_url: str) -> bytes:
        """Download a media attachment and return its raw bytes.

        Raises:
            MediaDownloadError: If the download fails or exceeds the size cap.
        """

        try:
            response = await self._request(
                "GET", media_url, expect_json=False
            )
        except WhatsAppAPIError as exc:
            raise MediaDownloadError(
                f"Failed to download media from {media_url}",
                media_url=media_url,
                original=exc,
            ) from exc
        content = getattr(response, "content", None)
        if content is None:
            raise MediaDownloadError(
                "Media response had no content", media_url=media_url
            )
        if len(content) > self.config.media_max_bytes:
            raise MediaDownloadError(
                f"Media exceeds max size ({len(content)} bytes)",
                media_url=media_url,
            )
        return content

    async def mark_as_read(self, message_id: str) -> dict[str, Any]:
        """Mark a message as read by its id."""

        return await self._request(
            "POST",
            "/api/v1/updateMessageReadStatus",
            params={"messageId": message_id, "status": "read"},
            json={"messageId": message_id},
        )

    async def health_check(self) -> bool:
        """Return True when the WATI API is reachable and authenticated."""

        if not self.config.is_configured:
            _log.info("WATI health_check: not configured")
            return False
        try:
            await self._request("GET", "/api/v1/getMessageTemplates")
            return True
        except WhatsAppAPIError as exc:
            _log.warning("WATI health_check failed: %s", exc)
            return False

    async def aclose(self) -> None:
        """Close the underlying pooled HTTP client, if one was created."""

        if self._client is not None:
            try:
                await self._client.aclose()
            finally:
                self._client = None

    async def __aenter__(self) -> "WATIClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()


# ---------------------------------------------------------------------------
# Response decoding helpers
# ---------------------------------------------------------------------------
def _decode(response: Any) -> Any:
    """Decode a response body to JSON, falling back to text/raw."""

    json_attr = getattr(response, "json", None)
    if callable(json_attr):
        try:
            return json_attr()
        except Exception:  # noqa: BLE001 - non-JSON body
            pass
    text = getattr(response, "text", None)
    return text if text is not None else response


def _safe_body(response: Any) -> Any:
    """Best-effort decode used when building error payloads."""

    try:
        return _decode(response)
    except Exception:  # noqa: BLE001 - defensive
        return None


# Public alias matching the problem statement / docs.
WhatsAppClient = WATIClient

__all__ = [
    "WATIClient",
    "WhatsAppClient",
    "SlidingWindowRateLimiter",
    "Transport",
]
