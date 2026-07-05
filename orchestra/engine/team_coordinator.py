"""Team coordination and outbound communication.

:class:`TeamCoordinator` is responsible for reaching people: notifying teams and
their leads, escalating to the CEO, and onboarding new project groups. It also
answers availability / workload questions and can suggest reassigning work when a
team is overloaded.

The actual message transport (WhatsApp) is provided via **dependency
injection**. Because the WhatsApp integration is a later phase, the coordinator
accepts any object satisfying the :class:`WhatsAppSender` protocol; when none is
supplied it degrades gracefully — messages are logged and recorded in the
communication log rather than sent — so the rest of the engine remains testable
and functional today.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from ..services.config import get_logger
from .exceptions import TeamNotFoundError

_log = get_logger(__name__)


@runtime_checkable
class WhatsAppSender(Protocol):
    """Minimal transport contract the coordinator depends on.

    A concrete WhatsApp service (Phase 4) only needs to implement these two
    coroutine methods to plug in.
    """

    async def send_message(self, to: str, message: str) -> Any:
        """Send a direct message to a phone number / contact."""

    async def send_group_message(self, group_id: str, message: str) -> Any:
        """Send a message to a WhatsApp group."""


class TeamCoordinator:
    """Async coordinator for team notifications and escalations."""

    def __init__(
        self,
        whatsapp_service: Optional[WhatsAppSender] = None,
        team_repo: Any = None,
        project_repo: Any = None,
        task_repo: Any = None,
        escalation_repo: Any = None,
        communication_repo: Any = None,
    ) -> None:
        self._whatsapp = whatsapp_service
        self._team_repo = team_repo
        self._project_repo = project_repo
        self._task_repo = task_repo
        self._escalation_repo = escalation_repo
        self._communication_repo = communication_repo

    # -- lazy dependency accessors -----------------------------------------
    @property
    def team_repo(self) -> Any:
        if self._team_repo is None:
            from ..database.repositories import TeamRepository

            self._team_repo = TeamRepository()
        return self._team_repo

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

    # -- transport ----------------------------------------------------------
    async def _dispatch(
        self,
        *,
        recipient: str,
        message: str,
        is_group: bool = False,
        company_id: Optional[Any] = None,
        project_id: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Send ``message`` via WhatsApp (if configured) and log it.

        Returns a small result dict describing whether the message was actually
        transmitted or only recorded.
        """

        delivered = False
        if self._whatsapp is not None and recipient:
            try:
                if is_group:
                    await self._whatsapp.send_group_message(recipient, message)
                else:
                    await self._whatsapp.send_message(recipient, message)
                delivered = True
            except Exception as exc:  # noqa: BLE001 - transport failures are non-fatal
                _log.error("WhatsApp send to %s failed: %s", recipient, exc)
        else:
            _log.info(
                "[no-transport] would send to %s: %s",
                recipient,
                message[:120],
            )

        await self._log_outbound(
            recipient=recipient,
            message=message,
            company_id=company_id,
            project_id=project_id,
        )
        return {"recipient": recipient, "delivered": delivered}

    async def _log_outbound(
        self,
        *,
        recipient: str,
        message: str,
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
                    "direction": "outbound",
                    "channel": "whatsapp",
                    "message_type": "text",
                    "recipient": recipient,
                    "content": message,
                }
            )
        except Exception as exc:  # noqa: BLE001 - logging must never break flow
            _log.debug("Failed to log outbound message: %s", exc)

    # -- notifications ------------------------------------------------------
    async def notify_team(self, team_id: Any, message: str) -> dict[str, Any]:
        """Notify a whole team (its WhatsApp group if known, else its lead)."""

        team = await self._get_team(team_id)
        metadata = team.metadata_ or {}
        group_id = metadata.get("group_id") if isinstance(metadata, dict) else None
        if group_id:
            return await self._dispatch(
                recipient=group_id,
                message=message,
                is_group=True,
                company_id=team.company_id,
            )
        # Fall back to the lead when there is no group.
        return await self._dispatch(
            recipient=team.lead_whatsapp or "",
            message=message,
            company_id=team.company_id,
        )

    async def notify_lead(self, team_id: Any, message: str) -> dict[str, Any]:
        """Send a direct message to the team lead."""

        team = await self._get_team(team_id)
        if not team.lead_whatsapp:
            _log.warning("Team id=%s has no lead_whatsapp configured", team_id)
        return await self._dispatch(
            recipient=team.lead_whatsapp or "",
            message=message,
            company_id=team.company_id,
        )

    async def notify_ceo(self, project_id: Any, message: str) -> dict[str, Any]:
        """Escalate a message to the CEO for a project.

        The CEO's contact is read from the company metadata
        (``ceo_whatsapp``/``escalation_number``) linked to the project.
        """

        project = await self.project_repo.get_project(project_id)
        company = getattr(project, "company", None)
        ceo_number = ""
        metadata = getattr(company, "metadata_", None) or {}
        if isinstance(metadata, dict):
            ceo_number = metadata.get("ceo_whatsapp") or metadata.get(
                "escalation_number", ""
            )
        if not ceo_number:
            ceo_number = getattr(company, "whatsapp_number", "") or ""
        return await self._dispatch(
            recipient=ceo_number,
            message=message,
            company_id=project.company_id,
            project_id=project_id,
        )

    async def send_welcome_message(
        self, group_id: str, project_id: Any
    ) -> dict[str, Any]:
        """Post an onboarding message to a new project's WhatsApp group."""

        project = await self.project_repo.get_project(project_id)
        message = (
            f"👋 Mudir is now coordinating *{project.name}*.\n"
            "I'll track stages, chase tasks and flag delays. "
            "Just tell me what happens and I'll keep everyone in sync."
        )
        return await self._dispatch(
            recipient=group_id,
            message=message,
            is_group=True,
            company_id=project.company_id,
            project_id=project_id,
        )

    # -- availability / workload -------------------------------------------
    async def get_team_availability(self, team_id: Any) -> dict[str, Any]:
        """Return whether a team is currently within its working hours.

        Working hours are read from team metadata as
        ``{"working_hours": {"start": 9, "end": 18, "days": [0-6]}}`` (hours in
        24h local time, days as ``0=Monday``). Missing config is treated as
        always-available.
        """

        team = await self._get_team(team_id)
        metadata = team.metadata_ or {}
        hours = metadata.get("working_hours") if isinstance(metadata, dict) else None
        now = datetime.now(timezone.utc)
        if not hours:
            return {"available": True, "reason": "no working-hours configured"}
        start = int(hours.get("start", 0))
        end = int(hours.get("end", 24))
        days = hours.get("days", list(range(7)))
        available = now.weekday() in days and start <= now.hour < end
        return {
            "available": available,
            "current_hour_utc": now.hour,
            "working_hours": hours,
        }

    async def get_team_workload(self, team_id: Any) -> dict[str, Any]:
        """Return the current task load for a team."""

        team = await self._get_team(team_id)
        tasks = await self.task_repo.get_tasks_by_team(team_id)
        counts = {"total": 0, "pending": 0, "in_progress": 0, "done": 0, "blocked": 0}
        for task in tasks:
            counts["total"] += 1
            status = str(getattr(task.status, "value", task.status))
            if status in counts:
                counts[status] += 1
        open_load = counts["pending"] + counts["in_progress"] + counts["blocked"]
        return {
            "team_id": str(team.id),
            "team_name": team.name,
            "counts": counts,
            "open_load": open_load,
        }

    async def suggest_team_reassignment(
        self, project_id: Any, stage_id: Any
    ) -> dict[str, Any]:
        """Suggest moving a stage's work to a less-loaded team.

        Compares the current stage owner's open workload against other active
        teams in the same company and recommends the least-loaded alternative
        when it is meaningfully lighter.
        """

        stages = await self.project_repo.get_stages(project_id)
        stage = next((s for s in stages if str(s.id) == str(stage_id)), None)
        if stage is None:
            return {"reassign": False, "reason": "stage not found"}

        project = await self.project_repo.get_project(project_id)
        teams = await self.team_repo.list(company_id=project.company_id, is_active=True)
        workloads: list[dict[str, Any]] = []
        for team in teams:
            workloads.append(await self.get_team_workload(team.id))
        if not workloads:
            return {"reassign": False, "reason": "no candidate teams"}

        workloads.sort(key=lambda w: w["open_load"])
        lightest = workloads[0]
        current = next(
            (w for w in workloads if stage.team_id and w["team_id"] == str(stage.team_id)),
            None,
        )
        if current is None:
            return {
                "reassign": True,
                "suggested_team_id": lightest["team_id"],
                "reason": "stage has no team assigned",
            }
        # Only recommend a move if it materially reduces load.
        if lightest["team_id"] != current["team_id"] and (
            current["open_load"] - lightest["open_load"] >= 2
        ):
            return {
                "reassign": True,
                "from_team_id": current["team_id"],
                "suggested_team_id": lightest["team_id"],
                "reason": (
                    f"current team load {current['open_load']} vs "
                    f"{lightest['open_load']}"
                ),
            }
        return {"reassign": False, "reason": "current team is not overloaded"}

    # -- helpers ------------------------------------------------------------
    async def _get_team(self, team_id: Any) -> Any:
        try:
            return await self.team_repo.get_team(team_id)
        except Exception as exc:
            raise TeamNotFoundError(team_id, original=exc) from exc


__all__ = ["TeamCoordinator", "WhatsAppSender"]
