"""Async repositories for the ORCHESTRA database layer.

Each repository encapsulates data access for a single aggregate and exposes a
small, task-oriented API. All methods are async, use context-managed sessions,
translate errors into :mod:`orchestra.database.exceptions`, log their
operations and are fully type-hinted.
"""

from __future__ import annotations

from .base import BaseRepository
from .communication_repository import CommunicationRepository
from .escalation_repository import EscalationRepository
from .learning_repository import LearningRepository
from .project_repository import ProjectRepository
from .task_repository import TaskRepository
from .team_repository import TeamRepository
from .whatsapp_repository import WhatsAppRepository
from .workflow_repository import WorkflowRepository

__all__ = [
    "BaseRepository",
    "ProjectRepository",
    "TaskRepository",
    "TeamRepository",
    "WorkflowRepository",
    "CommunicationRepository",
    "EscalationRepository",
    "LearningRepository",
    "WhatsAppRepository",
]
