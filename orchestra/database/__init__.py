"""ORCHESTRA database layer — Supabase (PostgreSQL) persistence.

A fully-async data access layer built on SQLAlchemy 2.0 + asyncpg, targeting
Supabase / PostgreSQL. It provides:

    * :mod:`models`            SQLAlchemy ORM models + enums
    * :mod:`connection`        async engine, pooling and session/transaction scopes
    * :mod:`supabase_client`   async Supabase facade (SQL + optional REST/realtime)
    * :mod:`repositories`      task-oriented async repositories per aggregate
    * :mod:`exceptions`        custom database exception hierarchy
    * :mod:`config`            environment-driven configuration

Quick start::

    from orchestra.database import get_supabase_client, ProjectRepository

    client = get_supabase_client()
    assert await client.health_check()

    repo = ProjectRepository()
    project = await repo.create_project({"name": "Store Opening", "company_id": cid})

Features: multi-tenancy (per-company isolation + RLS), soft deletes
(``is_active``), a full audit trail (``communication_logs``) and Supabase
real-time subscriptions via the optional REST client.
"""

from __future__ import annotations

from .config import DatabaseConfig, db_config, reload_config
from .connection import (
    ConnectionManager,
    dispose_engine,
    get_connection_manager,
    session_scope,
    transaction_scope,
)
from .exceptions import (
    ConnectionError,
    ConstraintViolationError,
    DatabaseError,
    DuplicateError,
    NotFoundError,
    TransactionError,
)
from .models import (
    Base,
    Company,
    CommunicationLog,
    Escalation,
    EscalationPriority,
    EscalationStatus,
    LearningData,
    MessageDirection,
    ModelCache,
    Project,
    ProjectStage,
    ProjectStatus,
    StageStatus,
    Task,
    TaskStatus,
    Team,
    WebhookStatus,
    Workflow,
    WhatsAppSession,
)
from .repositories import (
    CommunicationRepository,
    EscalationRepository,
    LearningRepository,
    ProjectRepository,
    TaskRepository,
    TeamRepository,
    WhatsAppRepository,
    WorkflowRepository,
)
from .supabase_client import SupabaseClient, get_supabase_client

__all__ = [
    # config
    "DatabaseConfig",
    "db_config",
    "reload_config",
    # connection
    "ConnectionManager",
    "get_connection_manager",
    "session_scope",
    "transaction_scope",
    "dispose_engine",
    # supabase client
    "SupabaseClient",
    "get_supabase_client",
    # exceptions
    "DatabaseError",
    "NotFoundError",
    "DuplicateError",
    "ConstraintViolationError",
    "ConnectionError",
    "TransactionError",
    # models / enums
    "Base",
    "Company",
    "Workflow",
    "Project",
    "ProjectStage",
    "Team",
    "Task",
    "Escalation",
    "CommunicationLog",
    "LearningData",
    "WhatsAppSession",
    "ModelCache",
    "ProjectStatus",
    "StageStatus",
    "TaskStatus",
    "EscalationPriority",
    "EscalationStatus",
    "MessageDirection",
    "WebhookStatus",
    # repositories
    "ProjectRepository",
    "TaskRepository",
    "TeamRepository",
    "WorkflowRepository",
    "CommunicationRepository",
    "EscalationRepository",
    "LearningRepository",
    "WhatsAppRepository",
]
