"""Project context and memory.

:class:`ContextManager` assembles the "working memory" the orchestrator and LLM
need to respond intelligently: the live project state, recent conversation, and
relevant historical patterns. It reads from the communication, learning and
project repositories and (optionally) the vector database for semantic recall of
similar past projects.
"""

from __future__ import annotations

from typing import Any, Optional

from ..services.config import get_logger
from .exceptions import ProjectNotFoundError

_log = get_logger(__name__)


class ContextManager:
    """Async assembler of project context and long-term memory."""

    def __init__(
        self,
        project_repo: Any = None,
        task_repo: Any = None,
        communication_repo: Any = None,
        learning_repo: Any = None,
        workflow_repo: Any = None,
        vector_db_service: Any = None,
    ) -> None:
        self._project_repo = project_repo
        self._task_repo = task_repo
        self._communication_repo = communication_repo
        self._learning_repo = learning_repo
        self._workflow_repo = workflow_repo
        self._vector_db = vector_db_service

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
    def communication_repo(self) -> Any:
        if self._communication_repo is None:
            from ..database.repositories import CommunicationRepository

            self._communication_repo = CommunicationRepository()
        return self._communication_repo

    @property
    def learning_repo(self) -> Any:
        if self._learning_repo is None:
            from ..database.repositories import LearningRepository

            self._learning_repo = LearningRepository()
        return self._learning_repo

    @property
    def workflow_repo(self) -> Any:
        if self._workflow_repo is None:
            from ..database.repositories import WorkflowRepository

            self._workflow_repo = WorkflowRepository()
        return self._workflow_repo

    @property
    def vector_db(self) -> Any:
        if self._vector_db is None:
            from ..services import vector_db_service

            self._vector_db = vector_db_service.get_service()
        return self._vector_db

    # -- context assembly ---------------------------------------------------
    async def get_project_context(self, project_id: Any) -> dict[str, Any]:
        """Return a rich context bundle for a project.

        Includes the project record, its stages and tasks, recent conversation
        and any stored ad-hoc context. Suitable for feeding to the LLM.

        Raises:
            ProjectNotFoundError: If the project does not exist.
        """

        try:
            project = await self.project_repo.get_project(project_id)
        except Exception as exc:
            raise ProjectNotFoundError(project_id, original=exc) from exc

        stages = await self.project_repo.get_stages(project_id)
        tasks = await self.task_repo.get_tasks_by_project(project_id)
        recent = await self.get_conversation_memory(project_id, limit=20)
        metadata = project.metadata_ or {}
        stored_context = (
            metadata.get("context", {}) if isinstance(metadata, dict) else {}
        )
        return {
            "project": {
                "id": str(project.id),
                "name": project.name,
                "status": str(getattr(project.status, "value", project.status)),
                "current_stage": project.current_stage,
                "location": project.location,
            },
            "stages": [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "status": str(getattr(s.status, "value", s.status)),
                    "team_id": str(s.team_id) if s.team_id else None,
                }
                for s in stages
            ],
            "tasks": [
                {
                    "id": str(t.id),
                    "title": t.title,
                    "status": str(getattr(t.status, "value", t.status)),
                }
                for t in tasks
            ],
            "recent_messages": recent,
            "stored_context": stored_context,
        }

    async def add_to_context(self, project_id: Any, key: str, value: Any) -> Any:
        """Persist an ad-hoc ``key``/``value`` into the project's context.

        The value is stored under ``metadata.context[key]`` on the project.
        """

        try:
            project = await self.project_repo.get_project(project_id)
        except Exception as exc:
            raise ProjectNotFoundError(project_id, original=exc) from exc
        metadata = dict(project.metadata_ or {})
        context = dict(metadata.get("context", {}))
        context[key] = value
        metadata["context"] = context
        return await self.project_repo.update(project_id, {"metadata_": metadata})

    async def get_conversation_memory(
        self, project_id: Any, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return the most recent messages for a project as plain dicts."""

        try:
            project = await self.project_repo.get_project(project_id)
        except Exception as exc:
            raise ProjectNotFoundError(project_id, original=exc) from exc
        logs = await self.communication_repo.get_conversation_history(
            project.company_id, project_id=project_id, limit=limit
        )
        return [
            {
                "direction": str(getattr(log.direction, "value", log.direction)),
                "sender": log.sender,
                "content": log.content,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]

    # -- historical patterns / suggestions ---------------------------------
    async def get_historical_patterns(
        self, company_id: Any, industry: Optional[str] = None
    ) -> dict[str, Any]:
        """Return learned workflows and observations for a company / industry."""

        workflows = await self.workflow_repo.get_active_workflows(company_id)
        if industry:
            workflows = [
                w
                for w in workflows
                if (w.metadata_ or {}).get("industry") == industry
                or industry.lower() in (w.name or "").lower()
            ]
        observations = await self.learning_repo.get_learning_data(company_id)
        return {
            "workflows": [
                {
                    "id": str(w.id),
                    "name": w.name,
                    "confidence": w.confidence,
                    "usage_count": w.usage_count,
                    "stages": list(w.stages or []),
                }
                for w in workflows
            ],
            "observations": [
                {
                    "type": o.observation_type,
                    "content": o.content,
                    "confidence": o.confidence,
                }
                for o in observations
            ],
        }

    async def suggest_based_on_history(self, project_id: Any) -> list[dict[str, Any]]:
        """Suggest next actions using stored suggestions + semantic recall.

        Combines high-confidence learning suggestions for the company with any
        semantically similar past projects found in the vector database.
        """

        try:
            project = await self.project_repo.get_project(project_id)
        except Exception as exc:
            raise ProjectNotFoundError(project_id, original=exc) from exc

        suggestions: list[dict[str, Any]] = []
        try:
            stored = await self.learning_repo.get_suggestions(project.company_id)
            for item in stored:
                suggestions.append(
                    {
                        "source": "learning",
                        "suggestion": item.suggestion,
                        "confidence": item.confidence,
                    }
                )
        except Exception as exc:  # noqa: BLE001 - suggestions are best-effort
            _log.debug("Learning suggestions unavailable: %s", exc)

        # Semantic recall of similar projects (optional).
        try:
            query = f"{project.name} {project.description or ''}".strip()
            similar = self.vector_db.search_text(query, limit=3)
            for hit in similar:
                if str(hit.get("id")) == str(project.id):
                    continue
                suggestions.append(
                    {
                        "source": "similar_project",
                        "reference": hit.get("id"),
                        "detail": hit.get("text"),
                    }
                )
        except Exception as exc:  # noqa: BLE001 - vector DB optional
            _log.debug("Vector recall unavailable: %s", exc)

        return suggestions


__all__ = ["ContextManager"]
