"""Repository for the :class:`Escalation` aggregate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import translate_error
from ..exceptions import NotFoundError
from ..models import Escalation, EscalationPriority, EscalationStatus
from .base import BaseRepository, _coerce_uuid

_OPEN_STATUSES = (EscalationStatus.PENDING, EscalationStatus.ACKNOWLEDGED)


class EscalationRepository(BaseRepository[Escalation]):
    """Data access for escalations (raised blockers)."""

    model = Escalation

    def __init__(self) -> None:
        super().__init__(Escalation)

    async def create_escalation(
        self,
        data: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> Escalation:
        """Create a new escalation from a plain ``data`` dict."""

        payload = dict(data)
        if payload.get("priority") is not None:
            payload["priority"] = EscalationPriority(payload["priority"])
        if payload.get("status") is not None:
            payload["status"] = EscalationStatus(payload["status"])
        self._log.info(
            "Creating escalation for project %s", payload.get("project_id")
        )
        return await self.add(Escalation(**payload), session=session)

    async def get_escalation(
        self,
        escalation_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Escalation:
        """Return the escalation or raise :class:`NotFoundError`."""

        return await self.get_or_raise(escalation_id, session=session)

    async def resolve_escalation(
        self,
        escalation_id: Any,
        *,
        resolution: Optional[str] = None,
        status: EscalationStatus | str = EscalationStatus.RESOLVED,
        session: Optional[AsyncSession] = None,
    ) -> Escalation:
        """Resolve (or dismiss) an escalation, stamping ``resolved_at``."""

        async with self._session(session) as sess:
            try:
                escalation = await sess.get(Escalation, _coerce_uuid(escalation_id))
                if escalation is None:
                    raise NotFoundError("Escalation", escalation_id)
                escalation.status = EscalationStatus(status)
                escalation.resolved_at = datetime.now(timezone.utc)
                if resolution is not None:
                    escalation.resolution = resolution
                await sess.flush()
                await sess.refresh(escalation)
                self._log.info(
                    "Resolved escalation %s -> %s", escalation_id, escalation.status
                )
                return escalation
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_pending_escalations(
        self,
        company_id: Optional[Any] = None,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[Escalation]:
        """Return open escalations (pending/acknowledged), highest priority first."""

        async with self._session(session) as sess:
            try:
                stmt = select(Escalation).where(
                    Escalation.status.in_(_OPEN_STATUSES)
                )
                if company_id is not None:
                    # Join through project for company scoping.
                    from ..models import Project

                    stmt = stmt.join(
                        Project, Escalation.project_id == Project.id
                    ).where(Project.company_id == _coerce_uuid(company_id))
                stmt = stmt.order_by(Escalation.created_at.asc())
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_escalations_by_project(
        self,
        project_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[Escalation]:
        """Return all escalations for a project (newest first)."""

        async with self._session(session) as sess:
            try:
                stmt = (
                    select(Escalation)
                    .where(Escalation.project_id == _coerce_uuid(project_id))
                    .order_by(Escalation.created_at.desc())
                )
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc


__all__ = ["EscalationRepository"]
