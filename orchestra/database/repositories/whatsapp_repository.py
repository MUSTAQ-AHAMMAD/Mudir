"""Repository for the :class:`WhatsAppSession` aggregate."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import translate_error
from ..exceptions import NotFoundError
from ..models import WebhookStatus, WhatsAppSession
from .base import BaseRepository, _coerce_uuid


class WhatsAppRepository(BaseRepository[WhatsAppSession]):
    """Data access for WhatsApp group sessions."""

    model = WhatsAppSession

    def __init__(self) -> None:
        super().__init__(WhatsAppSession)

    async def save_session(
        self,
        data: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> WhatsAppSession:
        """Create or update a session, keyed by its unique ``group_id``.

        If a session with the same ``group_id`` exists it is updated in place
        (upsert semantics); otherwise a new row is inserted.
        """

        payload = dict(data)
        if payload.get("webhook_status") is not None:
            payload["webhook_status"] = WebhookStatus(payload["webhook_status"])
        group_id = payload.get("group_id")
        async with self._session(session) as sess:
            try:
                existing = None
                if group_id is not None:
                    result = await sess.execute(
                        select(WhatsAppSession).where(
                            WhatsAppSession.group_id == group_id
                        )
                    )
                    existing = result.scalars().first()
                if existing is not None:
                    for key, value in payload.items():
                        setattr(existing, key, value)
                    await sess.flush()
                    await sess.refresh(existing)
                    self._log.info("Updated WhatsApp session group=%s", group_id)
                    return existing
                created = WhatsAppSession(**payload)
                sess.add(created)
                await sess.flush()
                await sess.refresh(created)
                self._log.info("Created WhatsApp session group=%s", group_id)
                return created
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_session_by_group(
        self,
        group_id: str,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Optional[WhatsAppSession]:
        """Return the session for a WhatsApp ``group_id`` or ``None``."""

        async with self._session(session) as sess:
            try:
                result = await sess.execute(
                    select(WhatsAppSession).where(
                        WhatsAppSession.group_id == group_id
                    )
                )
                return result.scalars().first()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def update_webhook_status(
        self,
        session_id: Any,
        status: WebhookStatus | str,
        *,
        session: Optional[AsyncSession] = None,
    ) -> WhatsAppSession:
        """Update a session's webhook status."""

        new_status = WebhookStatus(status)
        self._log.info("WhatsApp session %s webhook=%s", session_id, new_status)
        return await self.update(
            session_id, {"webhook_status": new_status}, session=session
        )

    async def deactivate_session(
        self,
        session_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> WhatsAppSession:
        """Soft-deactivate a session and disable its webhook."""

        async with self._session(session) as sess:
            try:
                row = await sess.get(WhatsAppSession, _coerce_uuid(session_id))
                if row is None:
                    raise NotFoundError("WhatsAppSession", session_id)
                row.is_active = False
                row.webhook_status = WebhookStatus.DISABLED
                await sess.flush()
                await sess.refresh(row)
                self._log.info("Deactivated WhatsApp session %s", session_id)
                return row
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc


__all__ = ["WhatsAppRepository"]
