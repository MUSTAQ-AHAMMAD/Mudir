"""ORCHESTRA orchestration engine — the coordination brain.

This package connects the self-hosted AI services
(:mod:`orchestra.services`) and the async database layer
(:mod:`orchestra.database`) into a single coordination engine. It learns
workflows from conversations, drives a universal state machine per project,
routes natural-language messages to command handlers, coordinates teams and runs
the periodic reminder / escalation / reporting jobs.

Modules:
    * :mod:`orchestrator`     THE MAIN ENGINE — wires everything together
    * :mod:`workflow_engine`  dynamic workflow learning
    * :mod:`state_machine`    universal, workflow-agnostic state machine
    * :mod:`project_manager`  project lifecycle
    * :mod:`task_manager`     task CRUD + smart assignment
    * :mod:`team_coordinator` team notifications / escalations
    * :mod:`intent_router`    intent detection + command routing
    * :mod:`context_manager`  project context and long-term memory
    * :mod:`scheduler`        dependency-free cron jobs
    * :mod:`exceptions`       engine-specific exception hierarchy

Quick start::

    from orchestra.engine import Orchestrator

    orchestrator = Orchestrator()
    result = await orchestrator.handle_incoming_message(
        message="We're opening a store in Riyadh Mall",
        sender="+966501234567",
        group_id="group123",
    )

The heavy AI / database dependencies are imported lazily by each component, so
importing this package is cheap and side-effect free.
"""

from __future__ import annotations

from .context_manager import ContextManager
from .exceptions import (
    AuthorizationError,
    EngineError,
    EscalationError,
    ProjectNotFoundError,
    SchedulingError,
    StateTransitionError,
    TaskNotFoundError,
    TeamNotFoundError,
    WorkflowError,
)
from .intent_router import INTENT_HANDLERS, IntentRouter
from .orchestrator import Orchestrator, get_orchestrator, reset_orchestrator
from .project_manager import ProjectManager
from .reputation import (
    NEUTRAL_SCORE,
    ReputationTracker,
    TaskOutcome,
    outcome_from_task,
    reputation_score,
)
from .scheduler import DEFAULT_WORKING_DAYS, ScheduledJob, Scheduler
from .state_machine import StateMachine
from .task_manager import TaskManager
from .team_coordinator import TeamCoordinator, WhatsAppSender
from .workflow_engine import WorkflowEngine, get_engine

__all__ = [
    # orchestrator
    "Orchestrator",
    "get_orchestrator",
    "reset_orchestrator",
    # components
    "WorkflowEngine",
    "get_engine",
    "StateMachine",
    "ProjectManager",
    "TaskManager",
    "ReputationTracker",
    "TaskOutcome",
    "outcome_from_task",
    "reputation_score",
    "NEUTRAL_SCORE",
    "TeamCoordinator",
    "WhatsAppSender",
    "IntentRouter",
    "INTENT_HANDLERS",
    "ContextManager",
    "Scheduler",
    "ScheduledJob",
    "DEFAULT_WORKING_DAYS",
    # exceptions
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
