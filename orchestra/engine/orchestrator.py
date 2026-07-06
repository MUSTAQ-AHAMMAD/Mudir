"""THE MAIN ENGINE — the orchestrator that connects AI + Database + Workflow.

:class:`Orchestrator` is the brain of ORCHESTRA. It receives messages (typically
from WhatsApp), understands them, and drives the whole coordination loop:
learning workflows, creating projects, advancing state machines, chasing tasks,
raising escalations and sending reminders.

Design patterns in play:

    * **Singleton** — :func:`get_orchestrator` returns one shared instance.
    * **Command** — :class:`~orchestra.engine.intent_router.IntentRouter` maps an
      intent to a handler method dispatched by :meth:`process_message_intent`.
    * **Strategy** — workflow learning is delegated to
      :class:`~orchestra.engine.workflow_engine.WorkflowEngine`.
    * **Dependency injection** — every collaborator (managers, coordinator,
      router, repositories, transport) can be supplied for testing; sensible
      lazy defaults are created otherwise.

Every public operation is asynchronous.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..services.config import get_logger
from .context_manager import ContextManager
from .exceptions import (
    EngineError,
    EscalationError,
    ProjectNotFoundError,
    WorkflowError,
)
from .intent_router import IntentRouter
from .project_manager import ProjectManager
from .scheduler import Scheduler
from .state_machine import StateMachine
from .task_manager import TaskManager
from .team_coordinator import TeamCoordinator, WhatsAppSender

_log = get_logger(__name__)


class Orchestrator:
    """The central coordination engine."""

    def __init__(
        self,
        *,
        whatsapp_service: Optional[WhatsAppSender] = None,
        workflow_engine: Any = None,
        project_manager: Optional[ProjectManager] = None,
        task_manager: Optional[TaskManager] = None,
        team_coordinator: Optional[TeamCoordinator] = None,
        intent_router: Optional[IntentRouter] = None,
        context_manager: Optional[ContextManager] = None,
        scheduler: Optional[Scheduler] = None,
        project_repo: Any = None,
        task_repo: Any = None,
        workflow_repo: Any = None,
        escalation_repo: Any = None,
        communication_repo: Any = None,
        whatsapp_repo: Any = None,
        learning_repo: Any = None,
    ) -> None:
        """Initialise all services (lazily wiring the AI + DB layers)."""

        from .workflow_engine import WorkflowEngine

        self.whatsapp_service = whatsapp_service
        self.workflow_engine = workflow_engine or WorkflowEngine()
        self.project_manager = project_manager or ProjectManager()
        self.task_manager = task_manager or TaskManager()
        self.team_coordinator = team_coordinator or TeamCoordinator(
            whatsapp_service=whatsapp_service
        )
        self.intent_router = intent_router or IntentRouter()
        self.context_manager = context_manager or ContextManager()
        self.scheduler = scheduler or Scheduler(orchestrator=self)

        # Injected repositories (lazy defaults via properties below).
        self._project_repo = project_repo
        self._task_repo = task_repo
        self._workflow_repo = workflow_repo
        self._escalation_repo = escalation_repo
        self._communication_repo = communication_repo
        self._whatsapp_repo = whatsapp_repo
        self._learning_repo = learning_repo
        _log.info("Orchestrator initialised")

    # -- lazy repository accessors -----------------------------------------
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
    def workflow_repo(self) -> Any:
        if self._workflow_repo is None:
            from ..database.repositories import WorkflowRepository

            self._workflow_repo = WorkflowRepository()
        return self._workflow_repo

    @property
    def escalation_repo(self) -> Any:
        if self._escalation_repo is None:
            from ..database.repositories import EscalationRepository

            self._escalation_repo = EscalationRepository()
        return self._escalation_repo

    @property
    def communication_repo(self) -> Any:
        if self._communication_repo is None:
            from ..database.repositories import CommunicationRepository

            self._communication_repo = CommunicationRepository()
        return self._communication_repo

    @property
    def whatsapp_repo(self) -> Any:
        if self._whatsapp_repo is None:
            from ..database.repositories import WhatsAppRepository

            self._whatsapp_repo = WhatsAppRepository()
        return self._whatsapp_repo

    @property
    def learning_repo(self) -> Any:
        if self._learning_repo is None:
            from ..database.repositories import LearningRepository

            self._learning_repo = LearningRepository()
        return self._learning_repo

    # ======================================================================
    # Main entry point
    # ======================================================================
    async def handle_incoming_message(
        self, message: str, sender: str, group_id: str
    ) -> dict[str, Any]:
        """MAIN ENTRY POINT — process one inbound message end to end.

        Resolves the company/project for ``group_id``, logs the message,
        classifies its intent, and routes it to the appropriate handler.

        Returns:
            A response dict, always containing at least a ``reply`` string.
        """

        _log.info("Incoming message from %s in group %s", sender, group_id)
        company_id, project_id = await self._resolve_group(group_id)
        await self._log_inbound(message, sender, company_id, project_id)

        classification = await self.intent_router.classify_intent(message)
        entities = await self.intent_router.extract_entities(message)
        intent_ctx: dict[str, Any] = {
            **classification,
            "message": message,
            "entities": entities,
            "company_id": company_id,
            "project_id": project_id,
        }
        try:
            return await self.process_message_intent(intent_ctx, sender, group_id)
        except EngineError as exc:
            _log.error("Engine error handling message: %s", exc)
            return {"reply": f"⚠️ {exc}", "error": str(exc)}

    async def process_message_intent(
        self, intent: dict[str, Any], sender: str, group_id: str
    ) -> dict[str, Any]:
        """Route a classified intent to the matching handler (Command pattern).

        Args:
            intent: The classification bundle produced by
                :meth:`handle_incoming_message` (intent, entities, message,
                resolved company/project ids).
            sender: Who sent the message.
            group_id: The originating WhatsApp group.
        """

        command = intent.get("intent", "natural_language")
        entities = intent.get("entities", {})
        message = intent.get("message", "")
        project_id = intent.get("project_id")
        route = self.intent_router.route_intent(command, entities, intent)
        _log.info("Routing command %r -> %s", command, route["handler"])

        if command == "create_project":
            return await self.create_new_project(message, sender, group_id)
        if command == "stage_complete" and project_id:
            stage_id = entities.get("stage_id") or entities.get("stage")
            return await self.handle_stage_completion(project_id, stage_id, sender)
        if command == "task_complete":
            task_id = entities.get("task_id") or entities.get("task")
            if task_id:
                return await self.handle_task_completion(task_id, sender)
        if command == "delay" and project_id:
            days = self._coerce_int(entities.get("days"), default=1)
            reason = entities.get("reason") or message
            return await self.handle_delay(project_id, days, reason, sender)
        if command == "escalation" and project_id:
            severity = str(entities.get("severity", "high"))
            reason = entities.get("reason") or message
            return await self.handle_escalation(project_id, reason, severity, sender)
        if command == "status" and project_id:
            return await self.get_project_status(project_id)
        if command == "add_task" and project_id:
            description = entities.get("task") or message
            team = entities.get("team_id") or entities.get("team")
            return await self.add_task(project_id, description, team, sender)

        # Fallback: free-form natural language.
        return await self.handle_natural_language(message, project_id, sender)

    # ======================================================================
    # Command handlers
    # ======================================================================
    async def create_new_project(
        self,
        message: Optional[str] = None,
        sender: Optional[str] = None,
        group_id: Optional[str] = None,
        *,
        name: Optional[str] = None,
        industry: Optional[str] = None,
        description: Optional[str] = None,
        company_id: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Learn a workflow from ``message`` and create a project around it.

        Accepts either a free-form ``message`` (from which the name/industry are
        inferred) or explicit ``name``/``industry`` keyword arguments.
        """

        if company_id is None and group_id:
            company_id, _ = await self._resolve_group(group_id)
        if company_id is None:
            raise ProjectNotFoundError("cannot resolve company for new project")

        source_text = message or name or ""
        if not source_text:
            raise WorkflowError("no text provided to create a project")

        # Strategy: learn the workflow dynamically.
        workflow_dict = await self.workflow_engine.learn_workflow(
            source_text, industry
        )
        project_name = name or workflow_dict.get("workflow_name") or "New Project"

        # Persist the learned workflow (unique per company+name).
        workflow_record = await self._persist_workflow(
            company_id, project_name, workflow_dict
        )

        project = await self.project_manager.create_project(
            name=project_name,
            description=description or (message if message != name else None),
            industry=industry,
            group_id=group_id,
            sender=sender,
            company_id=company_id,
            workflow_id=workflow_record.id,
        )

        # Materialise the workflow's stage templates as project stages.
        await self._materialise_stages(project.id, workflow_dict.get("stages", []))

        # Remember the active project on the group session for later messages.
        if group_id:
            await self._set_active_project(group_id, project.id)
            await self.team_coordinator.send_welcome_message(group_id, project.id)

        return {
            "reply": (
                f"✅ Created project *{project_name}* with "
                f"{len(workflow_dict.get('stages', []))} stages."
            ),
            "project_id": str(project.id),
            "workflow_id": str(workflow_record.id),
            "stages": workflow_dict.get("stages", []),
        }

    async def handle_stage_completion(
        self, project_id: Any, stage_id: Optional[Any], sender: Optional[str]
    ) -> dict[str, Any]:
        """Mark a stage complete and transition to the next available stage."""

        stages = list(await self.project_repo.get_stages(project_id))
        if not stages:
            raise WorkflowError("project has no stages to complete")
        machine = StateMachine(stages)

        # Resolve which stage was completed (explicit, else the active one).
        target = stage_id
        if target is None:
            current = machine.get_next_stage()
            target = current["id"] if current else None
        if target is None:
            return {"reply": "No active stage to complete."}

        resolved = machine._resolve(str(target))  # noqa: SLF001
        if resolved is None:
            return {"reply": f"Unknown stage: {target}"}

        await self.project_repo.complete_stage(resolved["id"])
        machine.complete_stage(resolved["id"])

        next_stage = machine.get_next_stage()
        if next_stage is None:
            await self.project_manager.update_project_status(project_id, "completed")
            return {
                "reply": "🎉 All stages complete — project finished!",
                "completed_stage": resolved["name"],
                "project_complete": True,
            }

        await self._update_stage(next_stage["id"], {"status": "in_progress"})
        await self.project_manager.update_project_status(
            project_id, "active", current_stage=next_stage["name"]
        )
        if next_stage.get("team_id"):
            await self.team_coordinator.notify_team(
                next_stage["team_id"],
                f"➡️ Stage *{next_stage['name']}* is now active. Please begin.",
            )
        return {
            "reply": (
                f"✅ Completed *{resolved['name']}*. "
                f"Next up: *{next_stage['name']}*."
            ),
            "completed_stage": resolved["name"],
            "next_stage": next_stage["name"],
        }

    async def handle_task_completion(
        self, task_id: Any, sender: Optional[str]
    ) -> dict[str, Any]:
        """Mark a task as complete."""

        task = await self.task_manager.get_task(task_id)
        await self.task_repo.complete_task(task_id)
        _log.info("Task %s completed by %s", task_id, sender)
        return {
            "reply": f"✅ Task *{task.title}* marked as done.",
            "task_id": str(task_id),
        }

    async def handle_delay(
        self,
        project_id: Any,
        days: int,
        reason: Optional[str],
        sender: Optional[str],
    ) -> dict[str, Any]:
        """Request an extension: push deadlines and record the delay."""

        project = await self.project_repo.get_project(project_id)
        metadata = dict(project.metadata_ or {})
        delays = list(metadata.get("delays", []))
        delays.append(
            {
                "days": days,
                "reason": reason,
                "requested_by": sender,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        metadata["delays"] = delays
        update: dict[str, Any] = {"metadata_": metadata}
        if project.opening_date is not None:
            update["opening_date"] = project.opening_date + timedelta(days=days)
        await self.project_repo.update(project_id, update)

        # A significant delay is escalated.
        if days >= 3:
            await self.handle_escalation(
                project_id,
                f"Delay of {days} days requested: {reason}",
                "medium",
                sender,
            )
        return {
            "reply": (
                f"🕒 Recorded a {days}-day delay"
                + (f" — {reason}" if reason else "")
                + "."
            ),
            "days": days,
        }

    async def handle_escalation(
        self,
        project_id: Any,
        reason: str,
        severity: str,
        sender: Optional[str],
    ) -> dict[str, Any]:
        """Escalate an issue to the CEO and record it."""

        priority = self._normalise_priority(severity)
        try:
            escalation = await self.escalation_repo.create_escalation(
                {
                    "project_id": project_id,
                    "reason": reason,
                    "priority": priority,
                    "raised_to": "ceo",
                    "metadata_": {"raised_by": sender},
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise EscalationError(
                f"could not create escalation: {exc}", original=exc
            ) from exc

        await self.team_coordinator.notify_ceo(
            project_id,
            f"🚨 *Escalation* ({priority}): {reason}",
        )
        return {
            "reply": f"🚨 Escalated to CEO ({priority}).",
            "escalation_id": str(escalation.id),
            "priority": priority,
        }

    async def get_project_status(self, project_id: Any) -> dict[str, Any]:
        """Generate a full status report for a project."""

        aggregate = await self.project_manager.get_project(project_id)
        project = aggregate["project"]
        stages = aggregate["stages"]
        tasks = aggregate["tasks"]

        report: dict[str, Any] = {
            "project_id": str(project.id),
            "name": project.name,
            "status": str(getattr(project.status, "value", project.status)),
        }
        if stages:
            machine = StateMachine(list(stages))
            report["workflow"] = machine.get_status_report()
        task_counts: dict[str, int] = {}
        for task in tasks:
            status = str(getattr(task.status, "value", task.status))
            task_counts[status] = task_counts.get(status, 0) + 1
        report["tasks"] = task_counts
        report["reply"] = self._format_status(report)
        return report

    async def handle_natural_language(
        self, message: str, project_id: Optional[Any], sender: Optional[str]
    ) -> dict[str, Any]:
        """Free-text fallback: answer using the LLM with project context."""

        context: dict[str, Any] = {"sender": sender}
        if project_id:
            try:
                context = await self.context_manager.get_project_context(project_id)
            except ProjectNotFoundError:
                pass
        reply = await self.intent_router.fallback_llm_response(message, context)
        return {"reply": reply}

    async def add_task(
        self,
        project_id: Any,
        description: str,
        assigned_team: Optional[Any],
        sender: Optional[str],
    ) -> dict[str, Any]:
        """Add a task, auto-assigning a team when none is given."""

        team_id = assigned_team
        if team_id is None:
            project = await self.project_repo.get_project(project_id)
            best = await self.task_manager.auto_assign_task(
                description, company_id=project.company_id
            )
            team_id = best.id if best is not None else None

        task = await self.task_manager.create_task(
            project_id=project_id,
            description=description,
            assigned_team=team_id,
        )
        if team_id is not None:
            await self.team_coordinator.notify_team(
                team_id, f"🆕 New task: {task.title}"
            )
        return {
            "reply": f"🆕 Added task *{task.title}*.",
            "task_id": str(task.id),
            "assigned_team": str(team_id) if team_id else None,
        }

    async def assign_team_to_stage(
        self, stage_id: Any, team_id: Optional[Any] = None
    ) -> dict[str, Any]:
        """Assign (or auto-assign) the best team to a stage."""

        stage = await self._get_stage(stage_id)
        if stage is None:
            raise WorkflowError(f"stage {stage_id!r} not found")

        if team_id is None:
            project = await self.project_repo.get_project(stage.project_id)
            best = await self.task_manager.auto_assign_task(
                stage.name, company_id=project.company_id
            )
            team_id = best.id if best is not None else None
        if team_id is None:
            return {"reply": "No suitable team found.", "assigned": False}

        await self._update_stage(stage_id, {"team_id": team_id})
        return {
            "reply": f"👥 Assigned team to stage *{stage.name}*.",
            "stage_id": str(stage_id),
            "team_id": str(team_id),
            "assigned": True,
        }

    async def generate_whatsapp_response(
        self, message: str, context: Optional[dict[str, Any]] = None
    ) -> str:
        """Format a human-friendly, WhatsApp-ready reply for ``message``."""

        return await self.intent_router.fallback_llm_response(message, context or {})

    # ======================================================================
    # Cron jobs
    # ======================================================================
    async def send_daily_reminders(self) -> dict[str, Any]:
        """09:00 job: remind teams of pending/overdue tasks per active project."""

        active = await self.project_repo.get_active_projects()
        reminded = 0
        for project in active:
            tasks = await self.task_repo.get_tasks_by_project(project.id)
            pending = [
                t
                for t in tasks
                if str(getattr(t.status, "value", t.status))
                in {"pending", "in_progress", "blocked"}
            ]
            for task in pending:
                if task.team_id is not None:
                    await self.team_coordinator.notify_team(
                        task.team_id,
                        f"⏰ Reminder: *{task.title}* is still open.",
                    )
                    reminded += 1
        _log.info("Daily reminders sent: %d", reminded)
        return {"projects": len(active), "reminders_sent": reminded}

    async def send_evening_escalations(self) -> dict[str, Any]:
        """18:00 job: escalate projects that are at risk (blocked/delayed)."""

        at_risk = await self.project_manager.get_projects_at_risk()
        escalated = 0
        for item in at_risk:
            project = item["project"]
            reasons = []
            if item["blockers"]:
                reasons.append(f"{len(item['blockers'])} blocker(s)")
            if item["delays"]:
                reasons.append(f"{len(item['delays'])} delayed stage(s)")
            try:
                await self.handle_escalation(
                    project.id,
                    "End-of-day risk review: " + ", ".join(reasons),
                    "medium",
                    "system",
                )
                escalated += 1
            except EngineError as exc:  # noqa: PERF203 - keep going on failure
                _log.error("Evening escalation failed for %s: %s", project.id, exc)
        return {"at_risk": len(at_risk), "escalated": escalated}

    async def send_weekly_report(self) -> dict[str, Any]:
        """Sunday job: send a weekly status summary to each project's CEO."""

        active = await self.project_repo.get_active_projects()
        sent = 0
        for project in active:
            status = await self.get_project_status(project.id)
            try:
                await self.team_coordinator.notify_ceo(
                    project.id,
                    "📊 *Weekly report*\n" + status.get("reply", ""),
                )
                sent += 1
            except EngineError as exc:  # noqa: PERF203
                _log.error("Weekly report failed for %s: %s", project.id, exc)
        return {"projects": len(active), "reports_sent": sent}

    async def run_monthly_learning(self) -> dict[str, Any]:
        """1st-of-month job: fold recent observations back into workflows."""

        workflows = await self.workflow_repo.get_active_workflows()
        improved = 0
        for workflow in workflows:
            try:
                await self.workflow_engine.improve_workflow(
                    workflow.id, {"stages": list(workflow.stages or [])}
                )
                improved += 1
            except EngineError as exc:  # noqa: PERF203
                _log.debug("Skipping workflow %s: %s", workflow.id, exc)
        return {"workflows": len(workflows), "improved": improved}

    async def start_scheduler(self) -> list[dict[str, Any]]:
        """Register all default cron jobs and return their descriptions."""

        self.scheduler.schedule_all_defaults()
        return self.scheduler.get_scheduled_jobs()

    # ======================================================================
    # Internal helpers
    # ======================================================================
    async def _resolve_group(self, group_id: str) -> tuple[Optional[Any], Optional[Any]]:
        """Return ``(company_id, active_project_id)`` for a WhatsApp group."""

        if not group_id:
            return None, None
        session = await self.whatsapp_repo.get_session_by_group(group_id)
        if session is None:
            return None, None
        company_id = session.company_id
        session_data = session.session_data or {}
        project_id = session_data.get("active_project_id")
        if project_id is None:
            # Fall back to the newest active project tagged with this group.
            active = await self.project_repo.get_active_projects(company_id)
            for project in active:
                if (project.metadata_ or {}).get("group_id") == group_id:
                    project_id = project.id
                    break
        return company_id, project_id

    async def _set_active_project(self, group_id: str, project_id: Any) -> None:
        """Persist the active project id on the group's WhatsApp session."""

        session = await self.whatsapp_repo.get_session_by_group(group_id)
        if session is None:
            _log.debug("No WhatsApp session for group %s; skipping", group_id)
            return
        data = dict(session.session_data or {})
        data["active_project_id"] = str(project_id)
        await self.whatsapp_repo.update(session.id, {"session_data": data})

    async def _log_inbound(
        self,
        message: str,
        sender: str,
        company_id: Optional[Any],
        project_id: Optional[Any],
    ) -> None:
        if company_id is None:
            return
        try:
            await self.communication_repo.log_message(
                {
                    "company_id": company_id,
                    "project_id": project_id,
                    "direction": "inbound",
                    "channel": "whatsapp",
                    "message_type": "text",
                    "sender": sender,
                    "content": message,
                }
            )
        except Exception as exc:  # noqa: BLE001 - logging must not break flow
            _log.debug("Failed to log inbound message: %s", exc)

    async def _persist_workflow(
        self, company_id: Any, name: str, workflow_dict: dict[str, Any]
    ) -> Any:
        """Create (or reuse) a workflow record for a learned workflow."""

        existing = await self.workflow_repo.get_workflows_by_company(company_id)
        for wf in existing:
            if (wf.name or "").strip().lower() == name.strip().lower():
                return wf
        return await self.workflow_repo.create_workflow(
            {
                "company_id": company_id,
                "name": name,
                "stages": workflow_dict.get("stages", []),
                "confidence": workflow_dict.get("confidence", 0.0),
                "metadata_": {"industry": workflow_dict.get("industry")},
            }
        )

    async def _materialise_stages(
        self, project_id: Any, stages: list[dict[str, Any]]
    ) -> None:
        """Create project stages from learned stage templates."""

        for sequence, stage in enumerate(stages):
            await self.project_repo.add_project_stage(
                project_id,
                {
                    "name": stage.get("name", f"Stage {sequence + 1}"),
                    "description": stage.get("description"),
                    "sequence": sequence,
                    "metadata_": {"depends_on": stage.get("depends_on", [])},
                },
            )

    async def _get_stage(self, stage_id: Any) -> Any:
        """Return a :class:`ProjectStage` by id via a managed session."""

        from ..database.connection import get_connection_manager
        from ..database.models import ProjectStage
        from ..database.repositories.base import _coerce_uuid

        async with get_connection_manager().session() as sess:
            return await sess.get(ProjectStage, _coerce_uuid(stage_id))

    async def _update_stage(self, stage_id: Any, values: dict[str, Any]) -> None:
        """Update a :class:`ProjectStage` (repos expose no generic stage update)."""

        from ..database.connection import get_connection_manager
        from ..database.models import ProjectStage
        from ..database.repositories.base import _coerce_uuid

        async with get_connection_manager().session() as sess:
            stage = await sess.get(ProjectStage, _coerce_uuid(stage_id))
            if stage is None:
                return
            for key, value in values.items():
                setattr(stage, key, value)
            await sess.flush()

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalise_priority(severity: str) -> str:
        mapping = {
            "low": "low",
            "medium": "medium",
            "med": "medium",
            "high": "high",
            "critical": "critical",
            "urgent": "critical",
        }
        return mapping.get(str(severity).strip().lower(), "high")

    @staticmethod
    def _format_status(report: dict[str, Any]) -> str:
        lines = [f"📋 *{report.get('name')}* — {report.get('status')}"]
        workflow = report.get("workflow")
        if workflow:
            lines.append(f"Progress: {workflow.get('progress_pct', 0)}%")
            if workflow.get("current_stage"):
                lines.append(f"Current stage: {workflow['current_stage']}")
            if workflow.get("blockers"):
                lines.append(f"⚠️ Blockers: {len(workflow['blockers'])}")
        tasks = report.get("tasks") or {}
        if tasks:
            summary = ", ".join(f"{k}: {v}" for k, v in tasks.items())
            lines.append(f"Tasks — {summary}")
        return "\n".join(lines)


# -- Singleton -------------------------------------------------------------
_default_orchestrator: Optional[Orchestrator] = None


def get_orchestrator(**kwargs: Any) -> Orchestrator:
    """Return the shared :class:`Orchestrator` singleton.

    The first call may pass constructor kwargs (e.g. a ``whatsapp_service``);
    subsequent calls return the same instance and ignore new kwargs.
    """

    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = Orchestrator(**kwargs)
    return _default_orchestrator


def reset_orchestrator() -> None:
    """Drop the singleton (primarily for tests)."""

    global _default_orchestrator
    _default_orchestrator = None


__all__ = ["Orchestrator", "get_orchestrator", "reset_orchestrator"]
