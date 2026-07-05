"""Project lifecycle management.

:class:`ProjectManager` is a thin, async orchestration layer over
:class:`orchestra.database.repositories.ProjectRepository` (plus the task
repository for aggregation). It owns project CRUD, soft-deletion, archiving and
the higher-level "at risk" / "by team" queries the coordinator needs.

Company scoping: projects are multi-tenant and require a ``company_id``. Callers
may pass one explicitly or let the manager resolve it from a WhatsApp
``group_id`` via the WhatsApp session table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from ..services.config import get_logger
from .exceptions import ProjectNotFoundError
from .state_machine import StateMachine

_log = get_logger(__name__)


class ProjectManager:
    """Async manager for the project lifecycle."""

    def __init__(
        self,
        project_repo: Any = None,
        task_repo: Any = None,
        whatsapp_repo: Any = None,
    ) -> None:
        self._project_repo = project_repo
        self._task_repo = task_repo
        self._whatsapp_repo = whatsapp_repo

    # -- lazy dependency accessors -----------------------------------------
    @property
    def project_repo(self) -> Any:
        if self._project_repo is None:
            from ..database.repositories import ProjectRepository

            self._project_repo = ProjectRepository()
        return self._project_repo

    @property
    def task_repo(self) -> Any:
        if self._task_repo is None:
            from ..database.repositories import TaskRepository

            self._task_repo = TaskRepository()
        return self._task_repo

    @property
    def whatsapp_repo(self) -> Any:
        if self._whatsapp_repo is None:
            from ..database.repositories import WhatsAppRepository

            self._whatsapp_repo = WhatsAppRepository()
        return self._whatsapp_repo

    # -- helpers ------------------------------------------------------------
    async def _resolve_company_id(
        self, company_id: Optional[Any], group_id: Optional[str]
    ) -> Any:
        """Resolve the owning company id from an explicit value or group id."""

        if company_id is not None:
            return company_id
        if group_id:
            session = await self.whatsapp_repo.get_session_by_group(group_id)
            if session is not None:
                return session.company_id
        raise ProjectNotFoundError(
            "cannot resolve company_id (pass company_id or a registered group_id)"
        )

    # -- CRUD ---------------------------------------------------------------
    async def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        industry: Optional[str] = None,
        group_id: Optional[str] = None,
        sender: Optional[str] = None,
        *,
        company_id: Optional[Any] = None,
        workflow_id: Optional[Any] = None,
        location: Optional[str] = None,
    ) -> Any:
        """Create a project and return the persisted record.

        Args:
            name: Human-readable project name.
            description: Optional longer description.
            industry: Optional industry tag stored in metadata.
            group_id: WhatsApp group id; used to resolve the company when
                ``company_id`` is not given.
            sender: Who initiated the project (stored in metadata).
            company_id: Explicit company id (overrides group-based resolution).
            workflow_id: Optional learned workflow to attach.
            location: Optional project location.
        """

        resolved_company = await self._resolve_company_id(company_id, group_id)
        metadata = {
            "industry": industry,
            "group_id": group_id,
            "created_by": sender,
        }
        data: dict[str, Any] = {
            "company_id": resolved_company,
            "name": name,
            "description": description,
            "location": location,
            "metadata_": {k: v for k, v in metadata.items() if v is not None},
        }
        if workflow_id is not None:
            data["workflow_id"] = workflow_id
        project = await self.project_repo.create_project(data)
        _log.info("Created project id=%s name=%r", project.id, name)
        return project

    async def get_project(self, project_id: Any) -> dict[str, Any]:
        """Return the full project aggregate (project + stages + tasks).

        Raises:
            ProjectNotFoundError: If the project does not exist.
        """

        try:
            project = await self.project_repo.get_project(project_id)
        except Exception as exc:  # NotFoundError from the DB layer
            raise ProjectNotFoundError(project_id, original=exc) from exc
        stages = await self.project_repo.get_stages(project_id)
        tasks = await self.task_repo.get_tasks_by_project(project_id)
        return {
            "project": project,
            "stages": list(stages),
            "tasks": list(tasks),
        }

    async def update_project_status(
        self,
        project_id: Any,
        status: Any,
        *,
        current_stage: Optional[str] = None,
    ) -> Any:
        """Update the overall status (and optionally current stage) of a project."""

        try:
            return await self.project_repo.update_project_status(
                project_id, status, current_stage=current_stage
            )
        except Exception as exc:
            raise ProjectNotFoundError(project_id, original=exc) from exc

    async def delete_project(self, project_id: Any) -> Any:
        """Soft-delete a project (sets ``is_active = False``)."""

        try:
            project = await self.project_repo.soft_delete(project_id)
        except Exception as exc:
            raise ProjectNotFoundError(project_id, original=exc) from exc
        _log.info("Soft-deleted project id=%s", project_id)
        return project

    async def archive_project(self, project_id: Any) -> Any:
        """Archive a project: flag it in metadata and deactivate it."""

        try:
            project = await self.project_repo.get_project(project_id)
        except Exception as exc:
            raise ProjectNotFoundError(project_id, original=exc) from exc
        metadata = dict(project.metadata_ or {})
        metadata["archived"] = True
        metadata["archived_at"] = datetime.now(timezone.utc).isoformat()
        updated = await self.project_repo.update(
            project_id, {"metadata_": metadata, "is_active": False}
        )
        _log.info("Archived project id=%s", project_id)
        return updated

    # -- queries ------------------------------------------------------------
    async def get_projects_by_status(
        self, status: Any, *, company_id: Optional[Any] = None
    ) -> Sequence[Any]:
        """Return projects filtered by ``status`` (optionally by company)."""

        filters: dict[str, Any] = {"status": status}
        if company_id is not None:
            filters["company_id"] = company_id
        return await self.project_repo.list(**filters)

    async def get_projects_at_risk(
        self, *, company_id: Optional[Any] = None
    ) -> list[dict[str, Any]]:
        """Return active projects that have blockers or delayed stages.

        Each entry pairs the project with the blockers/delays computed by the
        :class:`StateMachine` over its stages.
        """

        active = await self.project_repo.get_active_projects(company_id)
        at_risk: list[dict[str, Any]] = []
        for project in active:
            stages = await self.project_repo.get_stages(project.id)
            if not stages:
                continue
            machine = StateMachine(list(stages))
            blockers = machine.get_blockers()
            delays = machine.get_delays()
            if blockers or delays:
                at_risk.append(
                    {
                        "project": project,
                        "blockers": blockers,
                        "delays": delays,
                        "progress_pct": machine.get_progress(),
                    }
                )
        return at_risk

    async def get_projects_by_team(self, team_id: Any) -> list[Any]:
        """Return distinct projects that have tasks assigned to ``team_id``."""

        tasks = await self.task_repo.get_tasks_by_team(team_id)
        seen: dict[Any, Any] = {}
        for task in tasks:
            if task.project_id in seen:
                continue
            try:
                seen[task.project_id] = await self.project_repo.get_project(
                    task.project_id
                )
            except Exception:  # noqa: BLE001 - skip orphaned/deleted projects
                continue
        return list(seen.values())


__all__ = ["ProjectManager"]
