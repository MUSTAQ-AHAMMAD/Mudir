"""Task management.

:class:`TaskManager` wraps
:class:`orchestra.database.repositories.TaskRepository` (and the team repository
for smart assignment) with an async, orchestration-friendly API. It also offers
an embeddings-backed ``auto_assign_task`` that matches free-text task
descriptions to the most suitable team, degrading gracefully to keyword overlap
when the embeddings service is unavailable.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional, Sequence

from ..services.config import get_logger
from .exceptions import TaskNotFoundError

_log = get_logger(__name__)


class TaskManager:
    """Async manager for task CRUD and assignment."""

    def __init__(
        self,
        task_repo: Any = None,
        team_repo: Any = None,
        embeddings_service: Any = None,
    ) -> None:
        self._task_repo = task_repo
        self._team_repo = team_repo
        self._embeddings = embeddings_service

    # -- lazy dependency accessors -----------------------------------------
    @property
    def task_repo(self) -> Any:
        if self._task_repo is None:
            from ..database.repositories import TaskRepository

            self._task_repo = TaskRepository()
        return self._task_repo

    @property
    def team_repo(self) -> Any:
        if self._team_repo is None:
            from ..database.repositories import TeamRepository

            self._team_repo = TeamRepository()
        return self._team_repo

    @property
    def embeddings(self) -> Any:
        if self._embeddings is None:
            from ..services import embeddings_service

            self._embeddings = embeddings_service.get_service()
        return self._embeddings

    # -- CRUD ---------------------------------------------------------------
    async def create_task(
        self,
        project_id: Any,
        stage_id: Optional[Any] = None,
        description: str = "",
        assigned_team: Optional[Any] = None,
        deadline: Optional[date] = None,
    ) -> Any:
        """Create and persist a task, returning the record.

        The task ``title`` is derived from the first line/segment of
        ``description`` (the full text is kept in ``description``).
        """

        title = self._title_from(description)
        data: dict[str, Any] = {
            "project_id": project_id,
            "stage_id": stage_id,
            "title": title,
            "description": description or None,
            "team_id": assigned_team,
            "deadline": deadline,
        }
        task = await self.task_repo.create_task(
            {k: v for k, v in data.items() if v is not None}
        )
        _log.info("Created task id=%s project=%s", task.id, project_id)
        return task

    async def get_task(self, task_id: Any) -> Any:
        """Return a task or raise :class:`TaskNotFoundError`."""

        try:
            return await self.task_repo.get_task(task_id)
        except Exception as exc:
            raise TaskNotFoundError(task_id, original=exc) from exc

    async def update_task_status(self, task_id: Any, status: Any) -> Any:
        """Update a task's status."""

        try:
            return await self.task_repo.update_task_status(task_id, status)
        except Exception as exc:
            raise TaskNotFoundError(task_id, original=exc) from exc

    async def assign_task(
        self,
        task_id: Any,
        team_id: Optional[Any] = None,
        assignee: Optional[str] = None,
    ) -> Any:
        """Assign a task to a team and/or a specific person."""

        try:
            return await self.task_repo.assign_task(
                task_id, team_id=team_id, assigned_to=assignee
            )
        except Exception as exc:
            raise TaskNotFoundError(task_id, original=exc) from exc

    # -- queries ------------------------------------------------------------
    async def get_tasks_by_project(self, project_id: Any) -> Sequence[Any]:
        """Return all tasks for a project."""

        return await self.task_repo.get_tasks_by_project(project_id)

    async def get_tasks_by_team(self, team_id: Any) -> Sequence[Any]:
        """Return all tasks assigned to a team."""

        return await self.task_repo.get_tasks_by_team(team_id)

    async def get_overdue_tasks(
        self, *, company_id: Optional[Any] = None
    ) -> list[Any]:
        """Return unfinished tasks whose deadline is in the past.

        Args:
            company_id: When provided, results are limited to that company's
                projects. Otherwise all accessible tasks are scanned.
        """

        today = datetime.now(timezone.utc).date()
        if company_id is not None:
            from ..database.repositories import ProjectRepository

            projects = await ProjectRepository().get_active_projects(company_id)
            candidate: list[Any] = []
            for project in projects:
                candidate.extend(await self.task_repo.get_tasks_by_project(project.id))
        else:
            candidate = list(await self.task_repo.list())

        overdue: list[Any] = []
        for task in candidate:
            status = getattr(task.status, "value", task.status)
            if str(status) in {"done", "cancelled"}:
                continue
            if task.deadline is not None and task.deadline < today:
                overdue.append(task)
        return overdue

    # -- smart assignment ---------------------------------------------------
    async def auto_assign_task(
        self,
        task_description: str,
        skills_needed: Optional[Sequence[str]] = None,
        *,
        company_id: Optional[Any] = None,
    ) -> Optional[Any]:
        """Pick the best team for a task using semantic similarity.

        Builds a text profile for every candidate team (name, lead, member roles
        and any declared skills) and ranks them against the task description plus
        required skills. Falls back to keyword overlap when embeddings are
        unavailable.

        Returns:
            The best-matching team, or ``None`` if no teams are available.
        """

        teams = await self._candidate_teams(company_id)
        if not teams:
            return None

        query = task_description or ""
        if skills_needed:
            query = f"{query}\nRequired skills: {', '.join(skills_needed)}"

        profiles = [self._team_profile(team) for team in teams]
        try:
            scores = self._semantic_scores(query, profiles)
        except Exception as exc:  # noqa: BLE001 - embeddings optional
            _log.warning("Embeddings unavailable, falling back to keywords: %s", exc)
            scores = [self._keyword_score(query, profile) for profile in profiles]

        best_index = max(range(len(teams)), key=lambda i: scores[i])
        best_team = teams[best_index]
        _log.info(
            "Auto-assigned to team id=%s score=%.3f", best_team.id, scores[best_index]
        )
        return best_team

    async def _candidate_teams(self, company_id: Optional[Any]) -> list[Any]:
        filters: dict[str, Any] = {"is_active": True}
        if company_id is not None:
            filters["company_id"] = company_id
        return list(await self.team_repo.list(**filters))

    def _semantic_scores(self, query: str, profiles: list[str]) -> list[float]:
        query_vec = self.embeddings.generate_embedding(query)
        profile_vecs = self.embeddings.batch_generate_embeddings(profiles)
        return [
            self.embeddings.cosine_similarity(query_vec, vec) for vec in profile_vecs
        ]

    @staticmethod
    def _team_profile(team: Any) -> str:
        parts: list[str] = [getattr(team, "name", "") or ""]
        if getattr(team, "lead_name", None):
            parts.append(f"lead: {team.lead_name}")
        for member in getattr(team, "members", None) or []:
            if isinstance(member, dict):
                role = member.get("role") or ""
                name = member.get("name") or ""
                parts.append(f"{name} {role}".strip())
        metadata = getattr(team, "metadata_", None) or {}
        skills = metadata.get("skills") if isinstance(metadata, dict) else None
        if skills:
            parts.append("skills: " + ", ".join(str(s) for s in skills))
        return "\n".join(p for p in parts if p)

    @staticmethod
    def _keyword_score(query: str, profile: str) -> float:
        query_tokens = {t for t in query.lower().split() if len(t) > 2}
        profile_tokens = {t for t in profile.lower().split() if len(t) > 2}
        if not query_tokens or not profile_tokens:
            return 0.0
        return len(query_tokens & profile_tokens) / len(query_tokens)

    @staticmethod
    def _title_from(description: str, limit: int = 120) -> str:
        text = (description or "").strip()
        if not text:
            return "Untitled task"
        first_line = text.splitlines()[0].strip()
        return first_line[:limit] if first_line else text[:limit]


__all__ = ["TaskManager"]
