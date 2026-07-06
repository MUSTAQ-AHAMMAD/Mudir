"""Repository for the :class:`Workflow` aggregate."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import translate_error
from ..exceptions import NotFoundError
from ..models import Workflow
from .base import BaseRepository, _coerce_uuid


class WorkflowRepository(BaseRepository[Workflow]):
    """Data access for AI-learned workflows."""

    model = Workflow

    def __init__(self) -> None:
        super().__init__(Workflow)

    async def create_workflow(
        self,
        data: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> Workflow:
        """Create a new workflow from a plain ``data`` dict."""

        self._log.info("Creating workflow name=%r", data.get("name"))
        return await self.add(Workflow(**data), session=session)

    async def get_workflow(
        self,
        workflow_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Workflow:
        """Return the workflow or raise :class:`NotFoundError`."""

        return await self.get_or_raise(workflow_id, session=session)

    async def update_workflow(
        self,
        workflow_id: Any,
        values: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> Workflow:
        """Update arbitrary workflow fields."""

        self._log.info("Updating workflow %s", workflow_id)
        return await self.update(workflow_id, values, session=session)

    async def get_workflows_by_company(
        self,
        company_id: Any,
        *,
        include_inactive: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[Workflow]:
        """Return all workflows for a company (most-used first)."""

        async with self._session(session) as sess:
            try:
                stmt = select(Workflow).where(
                    Workflow.company_id == _coerce_uuid(company_id)
                )
                if not include_inactive:
                    stmt = stmt.where(Workflow.is_active.is_(True))
                stmt = stmt.order_by(Workflow.usage_count.desc())
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_active_workflows(
        self,
        company_id: Optional[Any] = None,
        *,
        min_confidence: float = 0.0,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[Workflow]:
        """Return active workflows above ``min_confidence``."""

        async with self._session(session) as sess:
            try:
                stmt = select(Workflow).where(
                    Workflow.is_active.is_(True),
                    Workflow.confidence >= min_confidence,
                )
                if company_id is not None:
                    stmt = stmt.where(Workflow.company_id == _coerce_uuid(company_id))
                stmt = stmt.order_by(Workflow.confidence.desc())
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def increment_usage_count(
        self,
        workflow_id: Any,
        *,
        amount: int = 1,
        session: Optional[AsyncSession] = None,
    ) -> Workflow:
        """Atomically increment a workflow's ``usage_count``."""

        async with self._session(session) as sess:
            try:
                workflow = await sess.get(Workflow, _coerce_uuid(workflow_id))
                if workflow is None:
                    raise NotFoundError("Workflow", workflow_id)
                workflow.usage_count = int(workflow.usage_count or 0) + amount
                await sess.flush()
                await sess.refresh(workflow)
                self._log.debug(
                    "Workflow %s usage_count=%s", workflow_id, workflow.usage_count
                )
                return workflow
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def update_confidence(
        self,
        workflow_id: Any,
        confidence: float,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Workflow:
        """Set a workflow's ``confidence`` (clamped to [0, 1])."""

        clamped = max(0.0, min(1.0, float(confidence)))
        self._log.info("Workflow %s confidence=%.3f", workflow_id, clamped)
        return await self.update(
            workflow_id, {"confidence": clamped}, session=session
        )


__all__ = ["WorkflowRepository"]
