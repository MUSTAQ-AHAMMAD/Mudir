"""WhatsAppSender — the outbound transport used by the orchestration engine.

:class:`WhatsAppSender` implements the ``WhatsAppSender`` protocol defined in
:mod:`orchestra.engine.team_coordinator` (``send_message`` +
``send_group_message``) so it can be injected straight into the
:class:`~orchestra.engine.orchestrator.Orchestrator`::

    from orchestra.engine import get_orchestrator
    from orchestra.whatsapp import WhatsAppSender

    orchestrator = get_orchestrator(whatsapp_service=WhatsAppSender())

On top of the protocol it exposes the higher-level helpers the platform needs
(templates, team / CEO notifications, onboarding, status updates). Every send:

* goes through :class:`~orchestra.whatsapp.client.WATIClient`,
* is recorded in ``communication_logs`` (best effort), and
* **falls back to logging** if the API call fails — so a transport outage never
  breaks the orchestration loop.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from . import templates as templates_module
from .client import WATIClient
from .config import get_logger
from .exceptions import RateLimitError, WhatsAppAPIError
from .session_manager import SessionManager

_log = get_logger(__name__)


class WhatsAppSender:
    """Concrete WhatsApp transport built on the WATI client."""

    def __init__(
        self,
        *,
        client: Optional[WATIClient] = None,
        session_manager: Optional[SessionManager] = None,
        communication_repo: Any = None,
        team_repo: Any = None,
        project_repo: Any = None,
    ) -> None:
        self._client = client
        self._session_manager = session_manager
        self._communication_repo = communication_repo
        self._team_repo = team_repo
        self._project_repo = project_repo

    # -- lazy dependency accessors -----------------------------------------
    @property
    def client(self) -> WATIClient:
        if self._client is None:
            self._client = WATIClient()
        return self._client

    @property
    def session_manager(self) -> SessionManager:
        if self._session_manager is None:
            self._session_manager = SessionManager(client=self.client)
        return self._session_manager

    @property
    def communication_repo(self) -> Any:
        if self._communication_repo is None:
            from ..database.repositories import CommunicationRepository

            self._communication_repo = CommunicationRepository()
        return self._communication_repo

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

    # ======================================================================
    # Protocol methods (used by TeamCoordinator / Orchestrator)
    # ======================================================================
    async def send_message(
        self,
        group_id: str,
        message: str,
        options: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Send ``message`` to a WhatsApp group / recipient.

        Implements the ``send_message`` half of the engine's ``WhatsAppSender``
        protocol. Returns a small result dict describing delivery.
        """

        return await self._deliver(
            recipient=group_id,
            message=message,
            is_group=True,
            options=options,
        )

    async def send_group_message(
        self,
        group_id: str,
        message: str,
        options: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Alias for :meth:`send_message` (protocol completeness)."""

        return await self.send_message(group_id, message, options)

    async def send_direct(
        self, phone_number: str, message: str
    ) -> dict[str, Any]:
        """Send a direct (1:1) message to ``phone_number``."""

        return await self._deliver(
            recipient=phone_number,
            message=message,
            is_group=False,
        )

    # ======================================================================
    # Higher-level helpers
    # ======================================================================
    async def send_template(
        self,
        group_id: str,
        template_name: str,
        variables: Optional[Mapping[str, Any]] = None,
        *,
        lang: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send a template message.

        When ``template_name`` maps to a Meta-approved template it is sent via
        WATI's template endpoint; otherwise the local bilingual template is
        rendered and sent as a normal session message.
        """

        vars_ = dict(variables or {})
        meta_name = templates_module.META_TEMPLATE_NAMES.get(template_name)
        company_id, project_id = await self._resolve_context(group_id)
        rendered = _try_render(template_name, vars_, lang)

        if meta_name and self.client.config.is_configured:
            try:
                result = await self.client.send_template(group_id, meta_name, vars_)
                await self._log_outbound(
                    group_id, rendered or meta_name, company_id, project_id,
                    message_type="template",
                )
                return {"recipient": group_id, "delivered": True, "result": result}
            except (WhatsAppAPIError, RateLimitError) as exc:
                _log.error("Template send failed, falling back to text: %s", exc)

        # Fallback: send the rendered bilingual text.
        text = rendered if rendered is not None else template_name
        return await self._deliver(
            recipient=group_id,
            message=text,
            is_group=True,
            message_type="template",
            company_id=company_id,
            project_id=project_id,
        )

    async def notify_team(self, team: Any, message: str) -> dict[str, Any]:
        """Notify a team via its WhatsApp group (falling back to its lead).

        ``team`` may be a group-id string, a team-like object exposing
        ``metadata_``/``lead_whatsapp``/``company_id``, or a team identifier
        that is looked up via the team repository.
        """

        group_id, recipient, is_group, company_id = await self._resolve_team_target(team)
        return await self._deliver(
            recipient=group_id or recipient,
            message=message,
            is_group=is_group,
            company_id=company_id,
        )

    async def notify_ceo(self, project_id: Any, message: str) -> dict[str, Any]:
        """Escalate ``message`` to the CEO for ``project_id``."""

        ceo_number = ""
        company_id: Optional[Any] = None
        try:
            project = await self.project_repo.get_project(project_id)
            company_id = getattr(project, "company_id", None)
            company = getattr(project, "company", None)
            metadata = getattr(company, "metadata_", None) or {}
            if isinstance(metadata, dict):
                ceo_number = metadata.get("ceo_whatsapp") or metadata.get(
                    "escalation_number", ""
                )
            if not ceo_number:
                ceo_number = getattr(company, "whatsapp_number", "") or ""
        except Exception as exc:  # noqa: BLE001 - resolution failures are non-fatal
            _log.error("Could not resolve CEO contact for project %s: %s", project_id, exc)
        return await self._deliver(
            recipient=ceo_number,
            message=message,
            is_group=False,
            company_id=company_id,
            project_id=project_id,
        )

    async def send_welcome(self, group_id: str, project: Any) -> dict[str, Any]:
        """Send the onboarding / welcome message to a new project group."""

        project_name = _project_name(project)
        team = _project_team(project)
        message = templates_module.render(
            "PROJECT_CREATED",
            {"project_name": project_name, "team": team},
        )
        company_id, project_id = await self._resolve_context(group_id)
        return await self._deliver(
            recipient=group_id,
            message=message,
            is_group=True,
            message_type="template",
            company_id=company_id,
            project_id=project_id,
        )

    async def send_status_update(
        self, group_id: str, status: Any
    ) -> dict[str, Any]:
        """Send a project status update to a group.

        ``status`` may be a pre-formatted string or a mapping that is rendered
        via the ``WEEKLY_SUMMARY`` template.
        """

        if isinstance(status, Mapping):
            message = templates_module.render(
                "WEEKLY_SUMMARY",
                {
                    "project_name": status.get("project_name", ""),
                    "summary": status.get("summary", ""),
                },
            )
        else:
            message = str(status)
        company_id, project_id = await self._resolve_context(group_id)
        return await self._deliver(
            recipient=group_id,
            message=message,
            is_group=True,
            company_id=company_id,
            project_id=project_id,
        )

    # ======================================================================
    # Internals
    # ======================================================================
    async def _deliver(
        self,
        *,
        recipient: str,
        message: str,
        is_group: bool,
        options: Optional[Mapping[str, Any]] = None,
        message_type: str = "text",
        company_id: Optional[Any] = None,
        project_id: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Send via the WATI client and log; fall back to logging on failure."""

        if company_id is None and is_group:
            company_id, project_id = await self._resolve_context(recipient)

        delivered = False
        error: Optional[str] = None
        result: Any = None
        if not recipient:
            _log.warning("Refusing to send message with empty recipient")
            error = "empty recipient"
        else:
            try:
                if is_group:
                    result = await self.client.send_message(recipient, message, options)
                else:
                    result = await self.client.send_direct_message(recipient, message)
                delivered = True
            except RateLimitError as exc:
                error = str(exc)
                _log.warning("Rate limited sending to %s: %s", recipient, exc)
            except WhatsAppAPIError as exc:
                error = str(exc)
                _log.error("WhatsApp send to %s failed: %s", recipient, exc)
            except Exception as exc:  # noqa: BLE001 - transport must never crash flow
                error = str(exc)
                _log.error("Unexpected send error to %s: %s", recipient, exc)

        if not delivered:
            _log.info("[fallback-log] to %s: %s", recipient, message[:160])

        await self._log_outbound(
            recipient, message, company_id, project_id, message_type=message_type
        )
        out: dict[str, Any] = {"recipient": recipient, "delivered": delivered}
        if error is not None:
            out["error"] = error
        if result is not None:
            out["result"] = result
        return out

    async def _log_outbound(
        self,
        recipient: str,
        message: str,
        company_id: Optional[Any],
        project_id: Optional[Any],
        *,
        message_type: str = "text",
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
                    "message_type": message_type,
                    "recipient": recipient,
                    "content": message,
                }
            )
        except Exception as exc:  # noqa: BLE001 - logging must never break flow
            _log.debug("Failed to log outbound message: %s", exc)

    async def _resolve_context(
        self, group_id: str
    ) -> tuple[Optional[Any], Optional[Any]]:
        """Resolve ``(company_id, project_id)`` for a group (best effort)."""

        try:
            company_id = await self.session_manager.get_company_for_group(group_id)
            project_id = await self.session_manager.get_project_for_group(group_id)
            return company_id, project_id
        except Exception as exc:  # noqa: BLE001 - context is optional
            _log.debug("Could not resolve context for group %s: %s", group_id, exc)
            return None, None

    async def _resolve_team_target(
        self, team: Any
    ) -> tuple[Optional[str], str, bool, Optional[Any]]:
        """Return ``(group_id, lead_number, is_group, company_id)`` for a team."""

        # A bare string is treated as a group id.
        if isinstance(team, str):
            return team, "", True, None

        resolved = team
        # Look up by identifier when we were not handed a team-like object.
        if not hasattr(team, "metadata_") and not hasattr(team, "lead_whatsapp"):
            try:
                resolved = await self.team_repo.get_team(team)
            except Exception as exc:  # noqa: BLE001 - fall back below
                _log.error("Could not resolve team %s: %s", team, exc)
                return None, "", False, None

        metadata = getattr(resolved, "metadata_", None) or {}
        group_id = metadata.get("group_id") if isinstance(metadata, dict) else None
        lead = getattr(resolved, "lead_whatsapp", "") or ""
        company_id = getattr(resolved, "company_id", None)
        if group_id:
            return group_id, "", True, company_id
        return None, lead, False, company_id


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _try_render(
    name: str, variables: Mapping[str, Any], lang: Optional[str]
) -> Optional[str]:
    try:
        return templates_module.render(name, variables, lang=lang)
    except Exception:  # noqa: BLE001 - unknown template -> no local text
        return None


def _project_name(project: Any) -> str:
    if isinstance(project, Mapping):
        return str(project.get("name", ""))
    return str(getattr(project, "name", "") or "")


def _project_team(project: Any) -> str:
    if isinstance(project, Mapping):
        return str(project.get("team", "") or "the team")
    return str(getattr(project, "team", "") or "the team")


__all__ = ["WhatsAppSender"]
