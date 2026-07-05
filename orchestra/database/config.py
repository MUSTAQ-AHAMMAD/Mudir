"""Configuration for the ORCHESTRA database layer.

All settings are sourced from environment variables so the layer can run
against a local PostgreSQL instance in development and a hosted Supabase
project in production without code changes. Import the module-level
:data:`db_config` singleton:

    from orchestra.database.config import db_config

    print(db_config.database_url)

The database URL is either taken verbatim from ``DATABASE_URL`` /
``SUPABASE_DB_URL`` or assembled from the individual ``DB_*`` components.
Supabase's Postgres connection string looks like::

    postgresql+asyncpg://postgres:<password>@db.<ref>.supabase.co:5432/postgres
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import cached_property
from urllib.parse import quote_plus

from ..services.config import get_logger

_log = get_logger(__name__)

# Async driver used for the SQLAlchemy engine.
_ASYNC_DRIVER = "postgresql+asyncpg"


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_opt(name: str) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning("Invalid int for %s=%r; using default %s", name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalise_async_url(url: str) -> str:
    """Coerce a plain Postgres URL to the async (asyncpg) driver form."""

    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", f"{_ASYNC_DRIVER}://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", f"{_ASYNC_DRIVER}://", 1)
    return url


@dataclass(frozen=True)
class DatabaseConfig:
    """Immutable configuration for the database layer."""

    # -- Direct URL (highest priority) --------------------------------------
    explicit_url: str | None = field(
        default_factory=lambda: _env_opt("DATABASE_URL") or _env_opt("SUPABASE_DB_URL")
    )

    # -- Individual components (fallback) -----------------------------------
    host: str = field(default_factory=lambda: _env("DB_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("DB_PORT", 5432))
    name: str = field(default_factory=lambda: _env("DB_NAME", "postgres"))
    user: str = field(default_factory=lambda: _env("DB_USER", "postgres"))
    password: str = field(default_factory=lambda: _env("DB_PASSWORD", "postgres"))

    # -- Supabase REST / realtime client ------------------------------------
    supabase_url: str | None = field(default_factory=lambda: _env_opt("SUPABASE_URL"))
    supabase_key: str | None = field(
        default_factory=lambda: _env_opt("SUPABASE_SERVICE_KEY")
        or _env_opt("SUPABASE_KEY")
        or _env_opt("SUPABASE_ANON_KEY")
    )

    # -- Connection pool -----------------------------------------------------
    pool_size: int = field(default_factory=lambda: _env_int("DB_POOL_SIZE", 10))
    max_overflow: int = field(default_factory=lambda: _env_int("DB_MAX_OVERFLOW", 20))
    pool_timeout: int = field(default_factory=lambda: _env_int("DB_POOL_TIMEOUT", 30))
    pool_recycle: int = field(default_factory=lambda: _env_int("DB_POOL_RECYCLE", 1800))
    pool_pre_ping: bool = field(default_factory=lambda: _env_bool("DB_POOL_PRE_PING", True))

    # -- Misc ----------------------------------------------------------------
    echo_sql: bool = field(default_factory=lambda: _env_bool("DB_ECHO", False))
    statement_timeout_ms: int = field(
        default_factory=lambda: _env_int("DB_STATEMENT_TIMEOUT_MS", 30000)
    )

    @cached_property
    def database_url(self) -> str:
        """Return the async SQLAlchemy database URL.

        Uses ``DATABASE_URL`` / ``SUPABASE_DB_URL`` when set, otherwise builds
        one from the individual ``DB_*`` components (URL-encoding the
        credentials).
        """

        if self.explicit_url:
            return _normalise_async_url(self.explicit_url)
        user = quote_plus(self.user)
        password = quote_plus(self.password)
        return f"{_ASYNC_DRIVER}://{user}:{password}@{self.host}:{self.port}/{self.name}"

    @cached_property
    def sync_database_url(self) -> str:
        """Return a synchronous (psycopg/libpq) URL, used by Alembic."""

        return self.database_url.replace(f"{_ASYNC_DRIVER}://", "postgresql://", 1)

    def safe_url(self) -> str:
        """Return the database URL with the password redacted (for logging)."""

        url = self.database_url
        if "@" not in url or "://" not in url:
            return url
        scheme, rest = url.split("://", 1)
        if "@" not in rest:
            return url
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0] if ":" in creds else creds
        return f"{scheme}://{user}:***@{host}"

    def has_supabase_client_config(self) -> bool:
        """Whether the Supabase REST/realtime client can be constructed."""

        return bool(self.supabase_url and self.supabase_key)


# Module-level singleton used across the database layer.
db_config = DatabaseConfig()


def reload_config() -> DatabaseConfig:
    """Rebuild the singleton from the current environment and return it."""

    global db_config
    db_config = DatabaseConfig()
    return db_config


__all__ = ["DatabaseConfig", "db_config", "reload_config", "get_logger"]
