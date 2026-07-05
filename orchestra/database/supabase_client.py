"""Async Supabase client wrapper for the ORCHESTRA database layer.

This ties together two ways of talking to Supabase:

    1. The **SQLAlchemy async engine** (via :mod:`.connection`) for pooled,
       transactional ORM access — the primary path used by repositories.
    2. The optional **Supabase Python client** (``supabase-py``) for REST /
       realtime features such as subscriptions and storage.

The ``supabase`` package is imported lazily so the rest of the database layer
works even when it is not installed (mirroring the lazy-ML-import convention of
``orchestra/services``).

    from orchestra.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    await client.health_check()
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Optional

from .config import DatabaseConfig, db_config, get_logger
from .connection import ConnectionManager, get_connection_manager
from .exceptions import ConnectionError as DBConnectionError

_log = get_logger(__name__)


class SupabaseClient:
    """Async facade over Supabase (SQLAlchemy engine + optional REST client)."""

    def __init__(
        self,
        config: Optional[DatabaseConfig] = None,
        connection_manager: Optional[ConnectionManager] = None,
    ) -> None:
        self._config = config or db_config
        self._connection = connection_manager or get_connection_manager()
        self._rest_client: Optional[Any] = None

    # -- connection manager passthrough -------------------------------------
    @property
    def connection(self) -> ConnectionManager:
        """The underlying SQLAlchemy async connection manager."""

        return self._connection

    def session(self) -> Any:
        """Return an async session context manager (auto commit/rollback)."""

        return self._connection.session()

    def transaction(self) -> Any:
        """Return an async transaction context manager (all-or-nothing)."""

        return self._connection.begin()

    async def transaction_scope(self) -> AsyncIterator[Any]:  # pragma: no cover
        """Deprecated alias retained for readability; prefer :meth:`transaction`."""

        async with self._connection.begin() as session:
            yield session

    # -- REST / realtime client --------------------------------------------
    def get_rest_client(self) -> Any:
        """Return a lazily-created ``supabase-py`` async client.

        Raises:
            DBConnectionError: If ``SUPABASE_URL`` / key are unset or the
                ``supabase`` package is not installed.
        """

        if self._rest_client is not None:
            return self._rest_client

        if not self._config.has_supabase_client_config():
            raise DBConnectionError(
                "SUPABASE_URL and a Supabase key are required for the REST client"
            )

        try:
            # Lazy import — the package is optional.
            from supabase import create_async_client  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise DBConnectionError(
                "The 'supabase' package is not installed; run "
                "`pip install supabase` to use the REST/realtime client",
                original=exc,
            ) from exc

        self._rest_client = create_async_client(
            self._config.supabase_url, self._config.supabase_key
        )
        return self._rest_client

    async def ensure_rest_client(self) -> Any:
        """Await and cache the async REST client factory result.

        ``supabase.create_async_client`` may return a coroutine depending on the
        installed version; this helper transparently awaits it when needed.
        """

        client = self.get_rest_client()
        if hasattr(client, "__await__"):
            client = await client  # type: ignore[assignment]
            self._rest_client = client
        return client

    # -- health -------------------------------------------------------------
    async def health_check(self) -> bool:
        """Return ``True`` when the database answers a trivial query."""

        return await self._connection.health_check()

    async def close(self) -> None:
        """Dispose of pooled connections held by the engine."""

        await self._connection.dispose()
        self._rest_client = None

    async def __aenter__(self) -> "SupabaseClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()


# Process-wide singleton.
_default_client: Optional[SupabaseClient] = None


def get_supabase_client() -> SupabaseClient:
    """Return the lazily-instantiated shared :class:`SupabaseClient`."""

    global _default_client
    if _default_client is None:
        _default_client = SupabaseClient()
    return _default_client


__all__ = ["SupabaseClient", "get_supabase_client"]
