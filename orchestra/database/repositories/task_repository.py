"""Repository for the :class:`Task` aggregate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import translate_error
from ..models import Task, TaskStatus
from .base import BaseRepository, _coerce_uuid


class TaskRepository(BaseRepository[Task]):
    """Data access for tasks."""

    model = Task

    def __init__(self) -> None:
        super().__init__(Task)

    async def create_task(
        self,
        data: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> Task:
        """Create a new task from a plain ``data`` dict."""

        self._log.info("Creating task title=%r", data.get("title"))
        return await self.add(Task(**data), session=session)

    async def get_task(
        self,
        task_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Task:
        """Return the task or raise :class:`NotFoundError`."""

        return await self.get_or_raise(task_id, session=session)

    async def update_task_status(
        self,
        task_id: Any,
        status: TaskStatus | str,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Task:
        """Update a task's status (stamping ``completed_at`` when done)."""

        new_status = TaskStatus(status)
        values: dict[str, Any] = {"status": new_status}
        if new_status is TaskStatus.DONE:
            values["completed_at"] = datetime.now(timezone.utc)
        self._log.info("Task %s -> status=%s", task_id, new_status)
        return await self.update(task_id, values, session=session)

    async def get_tasks_by_project(
        self,
        project_id: Any,
        *,
        status: Optional[TaskStatus | str] = None,
        include_inactive: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[Task]:
        """Return the tasks belonging to a project."""

        async with self._session(session) as sess:
            try:
                stmt = select(Task).where(Task.project_id == _coerce_uuid(project_id))
                if not include_inactive:
                    stmt = stmt.where(Task.is_active.is_(True))
                if status is not None:
                    stmt = stmt.where(Task.status == TaskStatus(status))
                stmt = stmt.order_by(Task.created_at)
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_tasks_by_team(
        self,
        team_id: Any,
        *,
        status: Optional[TaskStatus | str] = None,
        include_inactive: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[Task]:
        """Return the tasks assigned to a team."""

        async with self._session(session) as sess:
            try:
                stmt = select(Task).where(Task.team_id == _coerce_uuid(team_id))
                if not include_inactive:
                    stmt = stmt.where(Task.is_active.is_(True))
                if status is not None:
                    stmt = stmt.where(Task.status == TaskStatus(status))
                stmt = stmt.order_by(Task.deadline.nulls_last(), Task.created_at)
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def complete_task(
        self,
        task_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Task:
        """Mark a task done, stamping ``completed_at``."""

        return await self.update_task_status(
            task_id, TaskStatus.DONE, session=session
        )

    async def assign_task(
        self,
        task_id: Any,
        *,
        team_id: Optional[Any] = None,
        assigned_to: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> Task:
        """Assign a task to a team and/or a named individual."""

        values: dict[str, Any] = {}
        if team_id is not None:
            values["team_id"] = _coerce_uuid(team_id)
        if assigned_to is not None:
            values["assigned_to"] = assigned_to
        if not values:
            raise ValueError("assign_task requires team_id and/or assigned_to")
        self._log.info("Assigning task %s -> %s", task_id, values)
        return await self.update(task_id, values, session=session)


__all__ = ["TaskRepository"]
