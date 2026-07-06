"""Custom exceptions for the ORCHESTRA orchestration engine.

These wrap engine-level failures in a small, stable hierarchy so that callers
(the orchestrator, API handlers, WhatsApp webhook, cron jobs) can react to
failures without importing internal details. Every exception raised by the
engine package derives from :class:`EngineError`.

The database layer already exposes its own hierarchy in
:mod:`orchestra.database.exceptions`; these exceptions cover concerns that are
specific to orchestration — workflow learning, state transitions, authorisation,
escalation and scheduling.
"""

from __future__ import annotations

from typing import Optional


class EngineError(Exception):
    """Base class for every error raised by the orchestration engine.

    Args:
        message: Human-readable description of what went wrong.
        original: The underlying exception that triggered this error, if any.
    """

    def __init__(self, message: str, *, original: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.message = message
        self.original = original

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.original is not None:
            return (
                f"{self.message} "
                f"(caused by {type(self.original).__name__}: {self.original})"
            )
        return self.message


class WorkflowError(EngineError):
    """Raised when a workflow cannot be learned, validated or merged.

    Typical causes: an empty or malformed workflow, cyclic stage dependencies,
    or references to stages that do not exist.
    """


class StateTransitionError(EngineError):
    """Raised when a requested state-machine transition is not permitted.

    Args:
        stage_id: The stage the machine attempted to transition to.
        reason: Why the transition was rejected.
    """

    def __init__(
        self,
        message: str,
        *,
        stage_id: Optional[str] = None,
        reason: Optional[str] = None,
        original: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message, original=original)
        self.stage_id = stage_id
        self.reason = reason


class AuthorizationError(EngineError):
    """Raised when a sender is not permitted to perform the requested action."""


class ProjectNotFoundError(EngineError):
    """Raised when a project referenced by the engine does not exist."""

    def __init__(
        self,
        identifier: object = None,
        *,
        original: Optional[BaseException] = None,
    ) -> None:
        message = "Project not found"
        if identifier is not None:
            message = f"Project with identifier {identifier!r} not found"
        super().__init__(message, original=original)
        self.identifier = identifier


class TaskNotFoundError(EngineError):
    """Raised when a task referenced by the engine does not exist."""

    def __init__(
        self,
        identifier: object = None,
        *,
        original: Optional[BaseException] = None,
    ) -> None:
        message = "Task not found"
        if identifier is not None:
            message = f"Task with identifier {identifier!r} not found"
        super().__init__(message, original=original)
        self.identifier = identifier


class TeamNotFoundError(EngineError):
    """Raised when a team referenced by the engine does not exist."""

    def __init__(
        self,
        identifier: object = None,
        *,
        original: Optional[BaseException] = None,
    ) -> None:
        message = "Team not found"
        if identifier is not None:
            message = f"Team with identifier {identifier!r} not found"
        super().__init__(message, original=original)
        self.identifier = identifier


class EscalationError(EngineError):
    """Raised when an escalation cannot be created, routed or resolved."""


class SchedulingError(EngineError):
    """Raised when a scheduled job cannot be registered or executed."""


__all__ = [
    "EngineError",
    "WorkflowError",
    "StateTransitionError",
    "AuthorizationError",
    "ProjectNotFoundError",
    "TaskNotFoundError",
    "TeamNotFoundError",
    "EscalationError",
    "SchedulingError",
]
