"""Configuration for the ORCHESTRA WhatsApp integration (Phase 4).

All settings are sourced from environment variables with sensible defaults so
the integration can be imported and unit-tested without a live WATI account.
Import the module-level :data:`config` singleton::

    from orchestra.whatsapp.config import config

    print(config.wati_api_url)

The integration talks to WhatsApp Groups through the `WATI
<https://www.wati.io>`_ REST API. The following environment variables are
recognised (see also ``README`` / ``.env.example``)::

    WATI_API_URL          Base URL of the WATI live server
    WATI_API_KEY          ****** / access token for the WATI API
    WEBHOOK_SECRET        Shared secret used to sign/verify webhook payloads
    WEBHOOK_URL           Public URL WATI should POST events to
    WHATSAPP_RATE_LIMIT_PER_GROUP   Max messages / window / group
    WHATSAPP_RATE_LIMIT_PER_USER    Max messages / window / user
    WHATSAPP_RATE_LIMIT_WINDOW      Rate-limit window in seconds
    WHATSAPP_MEDIA_DOWNLOAD_TIMEOUT Seconds to wait for a media download
    WHATSAPP_TEMPLATE_NAMESPACE     Meta template namespace
    WHATSAPP_DEFAULT_LANG           Default template language ("ar" or "en")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import cached_property

# Re-use the services logging helpers so the whole platform logs uniformly.
from ..services.config import configure_logging, get_logger

__all__ = [
    "WhatsAppConfig",
    "config",
    "reload_config",
    "get_logger",
    "configure_logging",
]

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning("Invalid int for %s=%r; using default %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        _log.warning("Invalid float for %s=%r; using default %s", name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WhatsAppConfig:
    """Immutable configuration for the WhatsApp / WATI integration."""

    # -- WATI API -----------------------------------------------------------
    wati_api_url: str = field(
        default_factory=lambda: _env("WATI_API_URL", "https://live-server.wati.io")
    )
    wati_api_key: str = field(default_factory=lambda: _env("WATI_API_KEY", ""))

    # -- Webhook ------------------------------------------------------------
    webhook_secret: str = field(default_factory=lambda: _env("WEBHOOK_SECRET", ""))
    webhook_url: str = field(default_factory=lambda: _env("WEBHOOK_URL", ""))
    #: When True (default) an empty ``webhook_secret`` disables signature
    #: verification (useful for local development). In production always set a
    #: secret so this is a no-op.
    webhook_allow_unsigned: bool = field(
        default_factory=lambda: _env_bool("WEBHOOK_ALLOW_UNSIGNED", True)
    )

    # -- HTTP transport -----------------------------------------------------
    request_timeout: float = field(
        default_factory=lambda: _env_float("WHATSAPP_REQUEST_TIMEOUT", 30.0)
    )
    max_retries: int = field(
        default_factory=lambda: _env_int("WHATSAPP_MAX_RETRIES", 3)
    )
    retry_backoff_base: float = field(
        default_factory=lambda: _env_float("WHATSAPP_RETRY_BACKOFF", 0.5)
    )
    retry_backoff_max: float = field(
        default_factory=lambda: _env_float("WHATSAPP_RETRY_BACKOFF_MAX", 30.0)
    )
    #: Connection-pool limits for the underlying async HTTP client.
    pool_max_connections: int = field(
        default_factory=lambda: _env_int("WHATSAPP_POOL_MAX_CONNECTIONS", 20)
    )
    pool_max_keepalive: int = field(
        default_factory=lambda: _env_int("WHATSAPP_POOL_MAX_KEEPALIVE", 10)
    )

    # -- Rate limiting ------------------------------------------------------
    rate_limit_per_group: int = field(
        default_factory=lambda: _env_int("WHATSAPP_RATE_LIMIT_PER_GROUP", 20)
    )
    rate_limit_per_user: int = field(
        default_factory=lambda: _env_int("WHATSAPP_RATE_LIMIT_PER_USER", 10)
    )
    rate_limit_window: float = field(
        default_factory=lambda: _env_float("WHATSAPP_RATE_LIMIT_WINDOW", 60.0)
    )

    # -- Media --------------------------------------------------------------
    media_download_timeout: float = field(
        default_factory=lambda: _env_float("WHATSAPP_MEDIA_DOWNLOAD_TIMEOUT", 60.0)
    )
    media_max_bytes: int = field(
        default_factory=lambda: _env_int(
            "WHATSAPP_MEDIA_MAX_BYTES", 25 * 1024 * 1024
        )
    )

    # -- Templates ----------------------------------------------------------
    template_namespace: str = field(
        default_factory=lambda: _env("WHATSAPP_TEMPLATE_NAMESPACE", "")
    )
    default_lang: str = field(
        default_factory=lambda: _env("WHATSAPP_DEFAULT_LANG", "ar")
    )

    # -- Webhook server (optional middleware) -------------------------------
    webhook_request_timeout: float = field(
        default_factory=lambda: _env_float("WHATSAPP_WEBHOOK_TIMEOUT", 15.0)
    )

    # -- Derived properties -------------------------------------------------
    @cached_property
    def base_url(self) -> str:
        """WATI base URL without a trailing slash."""

        return self.wati_api_url.rstrip("/")

    @cached_property
    def is_configured(self) -> bool:
        """True when both an API URL and key are present (live mode)."""

        return bool(self.wati_api_url and self.wati_api_key)

    @cached_property
    def auth_header(self) -> dict[str, str]:
        """Authorization header for WATI requests.

        WATI accepts the access token as a ``Bearer`` token. If the configured
        key already includes the ``Bearer`` prefix it is used verbatim.
        """

        if not self.wati_api_key:
            return {}
        token = self.wati_api_key
        if not token.lower().startswith("bearer "):
            token = "Bearer " + token
        return {"Authorization": token}

    def summary(self) -> dict:
        """Return a JSON-serialisable snapshot (secrets redacted)."""

        return {
            "wati_api_url": self.wati_api_url,
            "wati_api_key": "***" if self.wati_api_key else "",
            "webhook_url": self.webhook_url,
            "webhook_secret": "***" if self.webhook_secret else "",
            "is_configured": self.is_configured,
            "rate_limit_per_group": self.rate_limit_per_group,
            "rate_limit_per_user": self.rate_limit_per_user,
            "rate_limit_window": self.rate_limit_window,
            "media_download_timeout": self.media_download_timeout,
            "template_namespace": self.template_namespace,
            "default_lang": self.default_lang,
        }


# Module-level singleton used across the whatsapp package.
config = WhatsAppConfig()


def reload_config() -> WhatsAppConfig:
    """Rebuild the singleton from the current environment and return it.

    Primarily useful in tests that mutate ``os.environ``.
    """

    global config
    config = WhatsAppConfig()
    return config
