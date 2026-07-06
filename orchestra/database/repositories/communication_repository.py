"""Repository for the append-only :class:`CommunicationLog` audit trail."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import translate_error
from ..models import CommunicationLog, MessageDirection
from .base import BaseRepository, _coerce_uuid


class CommunicationRepository(BaseRepository[CommunicationLog]):
    """Data access for the communication (message) audit log."""

    model = CommunicationLog

    def __init__(self) -> None:
        super().__init__(CommunicationLog)

    async def log_message(
        self,
        data: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> CommunicationLog:
        """Append a message to the audit trail.

        ``data`` must include ``company_id``; ``direction`` accepts either a
        :class:`MessageDirection` or its string value.
        """

        payload = dict(data)
        if "direction" in payload and payload["direction"] is not None:
            payload["direction"] = MessageDirection(payload["direction"])
        self._log.debug(
            "Logging %s message for company %s",
            payload.get("direction"),
            payload.get("company_id"),
        )
        return await self.add(CommunicationLog(**payload), session=session)

    async def get_conversation_history(
        self,
        company_id: Any,
        *,
        project_id: Optional[Any] = None,
        limit: int = 100,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[CommunicationLog]:
        """Return messages for a company (and optionally project) oldest-first."""

        async with self._session(session) as sess:
            try:
                stmt = select(CommunicationLog).where(
                    CommunicationLog.company_id == _coerce_uuid(company_id)
                )
                if project_id is not None:
                    stmt = stmt.where(
                        CommunicationLog.project_id == _coerce_uuid(project_id)
                    )
                stmt = stmt.order_by(CommunicationLog.created_at.asc()).limit(limit)
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_recent_messages(
        self,
        company_id: Any,
        *,
        limit: int = 20,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[CommunicationLog]:
        """Return the most recent messages for a company (newest-first)."""

        async with self._session(session) as sess:
            try:
                stmt = (
                    select(CommunicationLog)
                    .where(CommunicationLog.company_id == _coerce_uuid(company_id))
                    .order_by(CommunicationLog.created_at.desc())
                    .limit(limit)
                )
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def search_messages(
        self,
        company_id: Any,
        query: str,
        *,
        limit: int = 50,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[CommunicationLog]:
        """Case-insensitive substring search over message content/sender."""

        pattern = f"%{query}%"
        async with self._session(session) as sess:
            try:
                stmt = (
                    select(CommunicationLog)
                    .where(
                        CommunicationLog.company_id == _coerce_uuid(company_id),
                        or_(
                            CommunicationLog.content.ilike(pattern),
                            CommunicationLog.sender.ilike(pattern),
                        ),
                    )
                    .order_by(CommunicationLog.created_at.desc())
                    .limit(limit)
                )
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc


__all__ = ["CommunicationRepository"]
