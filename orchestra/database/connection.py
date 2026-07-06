"""Async connection management for the ORCHESTRA database layer.

This module owns the SQLAlchemy async engine and session factory. It exposes a
process-wide :class:`ConnectionManager` singleton plus convenience helpers:

    from orchestra.database.connection import session_scope

    async with session_scope() as session:
        session.add(obj)
        # commit happens automatically on clean exit

Connection pooling is configured from :data:`orchestra.database.config.db_config`.
"""

from __future__ import annotations

import contextlib
from typing import AsyncIterator, Optional

from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import DatabaseConfig, db_config, get_logger
from .exceptions import (
    ConnectionError as DBConnectionError,
    ConstraintViolationError,
    DatabaseError,
    DuplicateError,
    TransactionError,
)

_log = get_logger(__name__)


def build_database_url(config: Optional[DatabaseConfig] = None) -> str:
    """Return the async database URL from ``config`` (or the global default)."""

    return (config or db_config).database_url


def translate_error(exc: SQLAlchemyError) -> DatabaseError:
    """Map a SQLAlchemy error onto the ORCHESTRA exception hierarchy."""

    if isinstance(exc, IntegrityError):
        text = str(getattr(exc, "orig", exc)).lower()
        if "unique" in text or "duplicate" in text:
            return DuplicateError("Unique constraint violated", original=exc)
        return ConstraintViolationError("Constraint violated", original=exc)
    if isinstance(exc, OperationalError):
        return DBConnectionError("Database operational error", original=exc)
    if isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False):
        return DBConnectionError("Database connection invalidated", original=exc)
    return DatabaseError("Database error", original=exc)


class ConnectionManager:
    """Owns a single async engine + session factory for the process."""

    def __init__(self, config: Optional[DatabaseConfig] = None) -> None:
        self._config = config or db_config
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    # -- engine / factory ---------------------------------------------------
    @property
    def config(self) -> DatabaseConfig:
        return self._config

    def _create_engine(self) -> AsyncEngine:
        cfg = self._config
        _log.info("Creating async engine for %s", cfg.safe_url())
        connect_args: dict[str, object] = {}
        if cfg.statement_timeout_ms > 0:
            # asyncpg server settings must be strings.
            connect_args["server_settings"] = {
                "statement_timeout": str(cfg.statement_timeout_ms)
            }
        return create_async_engine(
            cfg.database_url,
            echo=cfg.echo_sql,
            pool_size=cfg.pool_size,
            max_overflow=cfg.max_overflow,
            pool_timeout=cfg.pool_timeout,
            pool_recycle=cfg.pool_recycle,
            pool_pre_ping=cfg.pool_pre_ping,
            connect_args=connect_args,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Return the lazily-created async engine."""

        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the lazily-created async session factory."""

        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
        return self._session_factory

    # -- sessions -----------------------------------------------------------
    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield an :class:`AsyncSession`, committing on success.

        Rolls back and translates SQLAlchemy errors into the ORCHESTRA
        exception hierarchy on failure. The session is always closed.
        """

        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as exc:
            await session.rollback()
            _log.error("Session rolled back due to error: %s", exc)
            raise translate_error(exc) from exc
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @contextlib.asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        """Yield a session bound to an explicit transaction block.

        Unlike :meth:`session`, the transaction is managed by SQLAlchemy's
        ``session.begin()`` context; use this when you want an all-or-nothing
        unit of work spanning multiple repository calls.
        """

        session = self.session_factory()
        try:
            async with session.begin():
                yield session
        except SQLAlchemyError as exc:
            _log.error("Transaction failed: %s", exc)
            raise translate_error(exc) from exc
        finally:
            await session.close()

    # -- lifecycle ----------------------------------------------------------
    async def health_check(self) -> bool:
        """Return ``True`` when a trivial ``SELECT 1`` succeeds."""

        from sqlalchemy import text

        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as exc:
            _log.warning("Database health check failed: %s", exc)
            return False

    async def dispose(self) -> None:
        """Dispose of the engine and its connection pool."""

        if self._engine is not None:
            await self._engine.dispose()
            _log.info("Database engine disposed")
            self._engine = None
            self._session_factory = None


# Process-wide singleton.
_manager: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """Return the lazily-instantiated shared :class:`ConnectionManager`."""

    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


def session_scope() -> contextlib.AbstractAsyncContextManager[AsyncSession]:
    """Convenience wrapper around :meth:`ConnectionManager.session`."""

    return get_connection_manager().session()


def transaction_scope() -> contextlib.AbstractAsyncContextManager[AsyncSession]:
    """Convenience wrapper around :meth:`ConnectionManager.begin`."""

    return get_connection_manager().begin()


async def dispose_engine() -> None:
    """Dispose the shared engine (call on application shutdown)."""

    if _manager is not None:
        await _manager.dispose()


__all__ = [
    "ConnectionManager",
    "get_connection_manager",
    "session_scope",
    "transaction_scope",
    "dispose_engine",
    "build_database_url",
    "translate_error",
    "TransactionError",
]
