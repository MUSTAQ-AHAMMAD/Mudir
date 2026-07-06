"""Base repository for the ORCHESTRA database layer.

Repositories encapsulate all data access for a single aggregate. They are
async, use context-managed sessions, translate errors into the ORCHESTRA
exception hierarchy, and log their operations.

Every method may be called either standalone (the repository opens and commits
its own session) or as part of a caller-supplied session/transaction — pass an
existing :class:`AsyncSession` to compose several repository calls into one
unit of work.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any, AsyncIterator, Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_logger
from ..connection import get_connection_manager, translate_error
from ..exceptions import NotFoundError
from ..models import Base

ModelT = TypeVar("ModelT", bound=Base)


def _coerce_uuid(value: Any) -> Any:
    """Return ``value`` as a :class:`uuid.UUID` when it is a UUID string."""

    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return value
    return value


class BaseRepository(Generic[ModelT]):
    """Generic async CRUD helper bound to a single ORM ``model``."""

    model: Type[ModelT]

    def __init__(self, model: Optional[Type[ModelT]] = None) -> None:
        if model is not None:
            self.model = model
        if not getattr(self, "model", None):
            raise TypeError("BaseRepository requires a 'model' attribute")
        self._log = get_logger(f"{__name__}.{self.model.__name__}")

    # -- session handling ---------------------------------------------------
    @contextlib.asynccontextmanager
    async def _session(
        self, session: Optional[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        """Yield ``session`` if provided, else open a self-managed session.

        When a session is supplied by the caller, commit/rollback is the
        caller's responsibility (it is left untouched here). Otherwise a new
        auto-committing session scope is opened.
        """

        if session is not None:
            yield session
        else:
            async with get_connection_manager().session() as owned:
                yield owned

    # -- generic CRUD -------------------------------------------------------
    async def add(
        self, instance: ModelT, *, session: Optional[AsyncSession] = None
    ) -> ModelT:
        """Persist ``instance`` and return it (refreshed)."""

        async with self._session(session) as sess:
            try:
                sess.add(instance)
                await sess.flush()
                await sess.refresh(instance)
                self._log.debug("Added %s id=%s", self.model.__name__, instance.id)
                return instance
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_by_id(
        self,
        entity_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Optional[ModelT]:
        """Return the row with ``entity_id`` or ``None``."""

        async with self._session(session) as sess:
            try:
                return await sess.get(self.model, _coerce_uuid(entity_id))
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_or_raise(
        self,
        entity_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> ModelT:
        """Return the row with ``entity_id`` or raise :class:`NotFoundError`."""

        found = await self.get_by_id(entity_id, session=session)
        if found is None:
            raise NotFoundError(self.model.__name__, entity_id)
        return found

    async def list(
        self,
        *,
        limit: Optional[int] = None,
        offset: int = 0,
        order_by: Any = None,
        session: Optional[AsyncSession] = None,
        **filters: Any,
    ) -> Sequence[ModelT]:
        """Return rows matching equality ``filters`` (with paging/ordering)."""

        async with self._session(session) as sess:
            try:
                stmt = select(self.model)
                for key, value in filters.items():
                    stmt = stmt.where(getattr(self.model, key) == _coerce_uuid(value))
                if order_by is not None:
                    stmt = stmt.order_by(order_by)
                if offset:
                    stmt = stmt.offset(offset)
                if limit is not None:
                    stmt = stmt.limit(limit)
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def update(
        self,
        entity_id: Any,
        values: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> ModelT:
        """Apply ``values`` to the row with ``entity_id`` and return it."""

        async with self._session(session) as sess:
            try:
                instance = await sess.get(self.model, _coerce_uuid(entity_id))
                if instance is None:
                    raise NotFoundError(self.model.__name__, entity_id)
                for key, value in values.items():
                    setattr(instance, key, value)
                await sess.flush()
                await sess.refresh(instance)
                self._log.debug("Updated %s id=%s", self.model.__name__, entity_id)
                return instance
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def delete(
        self,
        entity_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Hard-delete the row with ``entity_id``."""

        async with self._session(session) as sess:
            try:
                instance = await sess.get(self.model, _coerce_uuid(entity_id))
                if instance is None:
                    raise NotFoundError(self.model.__name__, entity_id)
                await sess.delete(instance)
                await sess.flush()
                self._log.debug("Deleted %s id=%s", self.model.__name__, entity_id)
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def soft_delete(
        self,
        entity_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> ModelT:
        """Set ``is_active = False`` on the row (requires the flag column)."""

        if not hasattr(self.model, "is_active"):
            raise AttributeError(
                f"{self.model.__name__} does not support soft deletes"
            )
        return await self.update(entity_id, {"is_active": False}, session=session)


__all__ = ["BaseRepository", "ModelT"]
