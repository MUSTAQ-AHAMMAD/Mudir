"""Repository for :class:`Project` and :class:`ProjectStage` aggregates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import translate_error
from ..exceptions import NotFoundError
from ..models import Project, ProjectStage, ProjectStatus, StageStatus
from .base import BaseRepository, _coerce_uuid

# Statuses considered "active" for dashboards / coordination.
_ACTIVE_STATUSES = (
    ProjectStatus.ACTIVE,
    ProjectStatus.ON_HOLD,
    ProjectStatus.BLOCKED,
)


class ProjectRepository(BaseRepository[Project]):
    """Data access for projects and their stages."""

    model = Project

    def __init__(self) -> None:
        super().__init__(Project)

    async def create_project(
        self,
        data: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> Project:
        """Create a new project from a plain ``data`` dict."""

        self._log.info("Creating project name=%r", data.get("name"))
        project = Project(**data)
        return await self.add(project, session=session)

    async def get_project(
        self,
        project_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Project:
        """Return the project or raise :class:`NotFoundError`."""

        return await self.get_or_raise(project_id, session=session)

    async def update_project_status(
        self,
        project_id: Any,
        status: ProjectStatus | str,
        *,
        current_stage: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> Project:
        """Update a project's ``status`` (and optionally ``current_stage``)."""

        values: dict[str, Any] = {"status": ProjectStatus(status)}
        if current_stage is not None:
            values["current_stage"] = current_stage
        self._log.info("Project %s -> status=%s", project_id, values["status"])
        return await self.update(project_id, values, session=session)

    async def get_projects_by_company(
        self,
        company_id: Any,
        *,
        include_inactive: bool = False,
        limit: Optional[int] = None,
        offset: int = 0,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[Project]:
        """Return all projects for a company (newest first)."""

        async with self._session(session) as sess:
            try:
                stmt = select(Project).where(
                    Project.company_id == _coerce_uuid(company_id)
                )
                if not include_inactive:
                    stmt = stmt.where(Project.is_active.is_(True))
                stmt = stmt.order_by(Project.created_at.desc()).offset(offset)
                if limit is not None:
                    stmt = stmt.limit(limit)
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_active_projects(
        self,
        company_id: Optional[Any] = None,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[Project]:
        """Return projects in an active lifecycle state."""

        async with self._session(session) as sess:
            try:
                stmt = select(Project).where(
                    Project.is_active.is_(True),
                    Project.status.in_(_ACTIVE_STATUSES),
                )
                if company_id is not None:
                    stmt = stmt.where(Project.company_id == _coerce_uuid(company_id))
                stmt = stmt.order_by(Project.created_at.desc())
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    # -- stages -------------------------------------------------------------
    async def add_project_stage(
        self,
        project_id: Any,
        data: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> ProjectStage:
        """Append a stage to a project, auto-assigning its sequence if absent."""

        async with self._session(session) as sess:
            try:
                project = await sess.get(Project, _coerce_uuid(project_id))
                if project is None:
                    raise NotFoundError("Project", project_id)
                payload = dict(data)
                payload.setdefault("project_id", project.id)
                if "sequence" not in payload:
                    max_seq = await sess.execute(
                        select(func.coalesce(func.max(ProjectStage.sequence), -1)).where(
                            ProjectStage.project_id == project.id
                        )
                    )
                    payload["sequence"] = int(max_seq.scalar_one()) + 1
                stage = ProjectStage(**payload)
                sess.add(stage)
                await sess.flush()
                await sess.refresh(stage)
                self._log.info(
                    "Added stage %r to project %s", stage.name, project_id
                )
                return stage
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def complete_stage(
        self,
        stage_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> ProjectStage:
        """Mark a stage completed, stamping ``completed_at``."""

        async with self._session(session) as sess:
            try:
                stage = await sess.get(ProjectStage, _coerce_uuid(stage_id))
                if stage is None:
                    raise NotFoundError("ProjectStage", stage_id)
                stage.status = StageStatus.COMPLETED
                stage.completed_at = datetime.now(timezone.utc)
                await sess.flush()
                await sess.refresh(stage)
                self._log.info("Completed stage %s", stage_id)
                return stage
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_stages(
        self,
        project_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[ProjectStage]:
        """Return a project's stages ordered by sequence."""

        async with self._session(session) as sess:
            try:
                stmt = (
                    select(ProjectStage)
                    .where(ProjectStage.project_id == _coerce_uuid(project_id))
                    .order_by(ProjectStage.sequence)
                )
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc


__all__ = ["ProjectRepository"]
