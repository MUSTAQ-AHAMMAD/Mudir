"""SQLAlchemy ORM models for the ORCHESTRA database layer.

These models map the multi-tenant coordination domain onto PostgreSQL /
Supabase. They are written for SQLAlchemy 2.0 using the typed ``Mapped`` /
``mapped_column`` declarative style.

Design notes:
    * **Multi-tenancy** — almost every table carries a ``company_id`` so rows
      are isolated per tenant; Row Level Security (see ``schema.sql``) enforces
      this at the database level.
    * **Soft deletes** — mutable tables expose an ``is_active`` flag instead of
      physically deleting rows.
    * **Audit trail** — :class:`CommunicationLog` is an append-only record of
      every inbound/outbound message.
    * **Flexible metadata** — a JSONB ``metadata_`` column (exposed as the
      ``metadata`` attribute) stores arbitrary structured data on most tables.
    * **Timestamps** — every table has ``created_at``; mutable tables also have
      ``updated_at`` which is refreshed on update.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Declarative base shared by every ORCHESTRA model."""


# ---------------------------------------------------------------------------
# Enums (used for status columns)
# ---------------------------------------------------------------------------
class ProjectStatus(str, enum.Enum):
    """Lifecycle state of a :class:`Project`."""

    DRAFT = "draft"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StageStatus(str, enum.Enum):
    """State of a single :class:`ProjectStage`."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class TaskStatus(str, enum.Enum):
    """State of a :class:`Task`."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class EscalationPriority(str, enum.Enum):
    """Urgency of an :class:`Escalation`."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationStatus(str, enum.Enum):
    """State of an :class:`Escalation`."""

    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class MessageDirection(str, enum.Enum):
    """Direction of a logged communication."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    SYSTEM = "system"


class WebhookStatus(str, enum.Enum):
    """Status of a WhatsApp webhook registration."""

    PENDING = "pending"
    ACTIVE = "active"
    FAILED = "failed"
    DISABLED = "disabled"


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------
def _pg_enum(enum_cls: type[enum.Enum], name: str) -> SQLEnum:
    """Build a native PG enum that persists member *values* (not names).

    SQLAlchemy defaults to storing ``Enum`` member *names*; our enums use
    lowercase string values that match ``schema.sql``, so we force the
    ``values_callable`` to emit ``member.value``.
    """

    return SQLEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at`` columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """Adds an ``is_active`` flag used for soft deletes."""

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


# ---------------------------------------------------------------------------
# Core tenant table
# ---------------------------------------------------------------------------
class Company(Base, TimestampMixin, SoftDeleteMixin):
    """A tenant. Everything else is scoped to a company."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(32))
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Riyadh", server_default="Asia/Riyadh"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    # Relationships
    workflows: Mapped[list["Workflow"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    teams: Mapped[list["Team"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    communication_logs: Mapped[list["CommunicationLog"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    whatsapp_sessions: Mapped[list["WhatsAppSession"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    learning_data: Mapped[list["LearningData"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_companies_slug", "slug"),)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Company id={self.id} slug={self.slug!r}>"


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------
class Workflow(Base, TimestampMixin, SoftDeleteMixin):
    """A reusable, AI-learned sequence of stages for a kind of project."""

    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # Ordered stage templates learned by the LLM, e.g.
    # [{"name": .., "description": .., "owner": .., "depends_on": [..]}]
    stages: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    usage_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    company: Mapped["Company"] = relationship(back_populates="workflows")
    projects: Mapped[list["Project"]] = relationship(back_populates="workflow")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_workflows_company_name"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_workflows_confidence_range"
        ),
        Index("idx_workflows_company_id", "company_id"),
        Index("idx_workflows_confidence", "confidence"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Workflow id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
class Project(Base, TimestampMixin, SoftDeleteMixin):
    """The coordination unit (e.g. a single store opening)."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="SET NULL")
    )
    code: Mapped[Optional[str]] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        _pg_enum(ProjectStatus, "project_status"),
        nullable=False,
        default=ProjectStatus.DRAFT,
        server_default=ProjectStatus.DRAFT.value,
    )
    current_stage: Mapped[Optional[str]] = mapped_column(String(255))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    opening_date: Mapped[Optional[date]] = mapped_column(Date)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    company: Mapped["Company"] = relationship(back_populates="projects")
    workflow: Mapped[Optional["Workflow"]] = relationship(back_populates="projects")
    stages: Mapped[list["ProjectStage"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectStage.sequence",
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    escalations: Mapped[list["Escalation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    communication_logs: Mapped[list["CommunicationLog"]] = relationship(
        back_populates="project"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_projects_company_code"),
        Index("idx_projects_status", "status"),
        Index("idx_projects_company_id", "company_id"),
        Index("idx_projects_workflow_id", "workflow_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Project id={self.id} name={self.name!r} status={self.status}>"


# ---------------------------------------------------------------------------
# ProjectStage
# ---------------------------------------------------------------------------
class ProjectStage(Base, TimestampMixin):
    """A single stage within a project's workflow instance."""

    __tablename__ = "project_stages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[StageStatus] = mapped_column(
        _pg_enum(StageStatus, "stage_status"),
        nullable=False,
        default=StageStatus.PENDING,
        server_default=StageStatus.PENDING.value,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    project: Mapped["Project"] = relationship(back_populates="stages")
    team: Mapped[Optional["Team"]] = relationship(back_populates="stages")

    __table_args__ = (
        Index("idx_project_stages_project_id", "project_id"),
        Index("idx_project_stages_status", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<ProjectStage id={self.id} name={self.name!r} status={self.status}>"


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------
class Team(Base, TimestampMixin, SoftDeleteMixin):
    """A team reachable over WhatsApp, with a lead and members."""

    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lead_name: Mapped[Optional[str]] = mapped_column(String(255))
    lead_whatsapp: Mapped[Optional[str]] = mapped_column(String(32))
    escalation_number: Mapped[Optional[str]] = mapped_column(String(32))
    # List of member objects, e.g. [{"name": .., "whatsapp": .., "role": ..}]
    members: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    company: Mapped["Company"] = relationship(back_populates="teams")
    tasks: Mapped[list["Task"]] = relationship(back_populates="team")
    stages: Mapped[list["ProjectStage"]] = relationship(back_populates="team")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_teams_company_name"),
        Index("idx_teams_company_id", "company_id"),
        Index("idx_teams_lead_whatsapp", "lead_whatsapp"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Team id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------
class Task(Base, TimestampMixin, SoftDeleteMixin):
    """A work item within a project, optionally owned by a team/stage."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL")
    )
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_stages.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[TaskStatus] = mapped_column(
        _pg_enum(TaskStatus, "task_status"),
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=TaskStatus.PENDING.value,
    )
    deadline: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    project: Mapped["Project"] = relationship(back_populates="tasks")
    team: Mapped[Optional["Team"]] = relationship(back_populates="tasks")
    escalations: Mapped[list["Escalation"]] = relationship(back_populates="task")

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_project_id", "project_id"),
        Index("idx_tasks_team_id", "team_id"),
        Index("idx_tasks_deadline", "deadline"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Task id={self.id} title={self.title!r} status={self.status}>"


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------
class Escalation(Base, TimestampMixin):
    """A raised blocker that needs attention from a lead / manager."""

    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[EscalationPriority] = mapped_column(
        _pg_enum(EscalationPriority, "escalation_priority"),
        nullable=False,
        default=EscalationPriority.MEDIUM,
        server_default=EscalationPriority.MEDIUM.value,
    )
    status: Mapped[EscalationStatus] = mapped_column(
        _pg_enum(EscalationStatus, "escalation_status"),
        nullable=False,
        default=EscalationStatus.PENDING,
        server_default=EscalationStatus.PENDING.value,
    )
    raised_to: Mapped[Optional[str]] = mapped_column(String(255))
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    project: Mapped["Project"] = relationship(back_populates="escalations")
    task: Mapped[Optional["Task"]] = relationship(back_populates="escalations")

    __table_args__ = (
        Index("idx_escalations_project_id", "project_id"),
        Index("idx_escalations_status", "status"),
        Index("idx_escalations_priority", "priority"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Escalation id={self.id} status={self.status} priority={self.priority}>"


# ---------------------------------------------------------------------------
# CommunicationLog (append-only audit trail)
# ---------------------------------------------------------------------------
class CommunicationLog(Base):
    """Append-only record of every inbound/outbound/system message."""

    __tablename__ = "communication_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL")
    )
    direction: Mapped[MessageDirection] = mapped_column(
        _pg_enum(MessageDirection, "message_direction"),
        nullable=False,
        default=MessageDirection.INBOUND,
        server_default=MessageDirection.INBOUND.value,
    )
    channel: Mapped[str] = mapped_column(
        String(32), nullable=False, default="whatsapp", server_default="whatsapp"
    )
    message_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="text", server_default="text"
    )
    sender: Mapped[Optional[str]] = mapped_column(String(255))
    recipient: Mapped[Optional[str]] = mapped_column(String(255))
    content: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    company: Mapped["Company"] = relationship(back_populates="communication_logs")
    project: Mapped[Optional["Project"]] = relationship(back_populates="communication_logs")

    __table_args__ = (
        Index("idx_communication_logs_created_at", "created_at"),
        Index("idx_communication_logs_company_id", "company_id"),
        Index("idx_communication_logs_project_id", "project_id"),
        Index("idx_communication_logs_sender", "sender"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<CommunicationLog id={self.id} direction={self.direction}>"


# ---------------------------------------------------------------------------
# LearningData
# ---------------------------------------------------------------------------
class LearningData(Base, TimestampMixin):
    """AI observations, learned patterns and improvement suggestions."""

    __tablename__ = "learning_data"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE")
    )
    observation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    suggestion: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    is_implemented: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    implemented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    company: Mapped[Optional["Company"]] = relationship(back_populates="learning_data")

    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_learning_confidence_range"
        ),
        Index("idx_learning_data_confidence", "confidence"),
        Index("idx_learning_data_company_id", "company_id"),
        Index("idx_learning_data_type", "observation_type"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<LearningData id={self.id} type={self.observation_type!r}>"


# ---------------------------------------------------------------------------
# WhatsAppSession
# ---------------------------------------------------------------------------
class WhatsAppSession(Base, TimestampMixin, SoftDeleteMixin):
    """A WhatsApp group mapped to a company for coordination."""

    __tablename__ = "whatsapp_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    group_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone_number: Mapped[Optional[str]] = mapped_column(String(32))
    webhook_status: Mapped[WebhookStatus] = mapped_column(
        _pg_enum(WebhookStatus, "webhook_status"),
        nullable=False,
        default=WebhookStatus.PENDING,
        server_default=WebhookStatus.PENDING.value,
    )
    session_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    company: Mapped["Company"] = relationship(back_populates="whatsapp_sessions")

    __table_args__ = (
        Index("idx_whatsapp_sessions_group_id", "group_id"),
        Index("idx_whatsapp_sessions_company_id", "company_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<WhatsAppSession id={self.id} group_id={self.group_id!r}>"


# ---------------------------------------------------------------------------
# ModelCache
# ---------------------------------------------------------------------------
class ModelCache(Base):
    """Cache of AI model outputs keyed by an input hash, with expiry."""

    __tablename__ = "model_cache"

    id: Mapped[uuid.UUID] = _uuid_pk()
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(255))
    input_hash: Mapped[Optional[str]] = mapped_column(String(128))
    output: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    hits: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_model_cache_cache_key", "cache_key"),
        Index("idx_model_cache_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<ModelCache id={self.id} cache_key={self.cache_key!r}>"


__all__ = [
    "Base",
    # Enums
    "ProjectStatus",
    "StageStatus",
    "TaskStatus",
    "EscalationPriority",
    "EscalationStatus",
    "MessageDirection",
    "WebhookStatus",
    # Mixins
    "TimestampMixin",
    "SoftDeleteMixin",
    # Models
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
]
