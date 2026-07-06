"""WhatsApp group session management.

A *session* maps a WhatsApp group to a company (and optionally an active
project) so the orchestrator can resolve who a message belongs to. This module
is a thin, async coordination layer over
:class:`orchestra.database.repositories.WhatsAppRepository`, following the same
lazy-import / dependency-injection pattern as the engine.

Group membership (which phone numbers are in a group) is cached in the
session's ``session_data`` JSON and can be refreshed from the live WATI API via
:meth:`sync_group_members`.
"""

from __future__ import annotations

from typing import Any, Optional

from .client import WATIClient
from .config import get_logger
from .exceptions import SessionNotFoundError

_log = get_logger(__name__)


class SessionManager:
    """Manage the mapping between WhatsApp groups and company/project state."""

    def __init__(
        self,
        *,
        whatsapp_repo: Any = None,
        client: Optional[WATIClient] = None,
    ) -> None:
        self._whatsapp_repo = whatsapp_repo
        self._client = client

    # -- lazy dependency accessors -----------------------------------------
    @property
    def whatsapp_repo(self) -> Any:
        if self._whatsapp_repo is None:
            from ..database.repositories import WhatsAppRepository

            self._whatsapp_repo = WhatsAppRepository()
        return self._whatsapp_repo

    @property
    def client(self) -> WATIClient:
        if self._client is None:
            self._client = WATIClient()
        return self._client

    # -- registration -------------------------------------------------------
    async def register_group(
        self,
        group_id: str,
        company_id: Any,
        project_id: Optional[Any] = None,
        *,
        group_name: Optional[str] = None,
        phone_number: Optional[str] = None,
    ) -> Any:
        """Create or update the session for ``group_id`` (upsert)."""

        session_data: dict[str, Any] = {}
        if project_id is not None:
            session_data["active_project_id"] = str(project_id)
        payload: dict[str, Any] = {
            "group_id": group_id,
            "company_id": company_id,
            "group_name": group_name,
            "phone_number": phone_number,
            "webhook_status": "active",
            "is_active": True,
            "session_data": session_data,
        }
        _log.info("Registering WhatsApp group %s -> company %s", group_id, company_id)
        return await self.whatsapp_repo.save_session(payload)

    # -- lookups ------------------------------------------------------------
    async def _get_session_or_raise(self, group_id: str) -> Any:
        session = await self.whatsapp_repo.get_session_by_group(group_id)
        if session is None:
            raise SessionNotFoundError(group_id)
        return session

    async def get_project_for_group(self, group_id: str) -> Optional[Any]:
        """Return the active project id for ``group_id`` (or ``None``)."""

        session = await self.whatsapp_repo.get_session_by_group(group_id)
        if session is None:
            return None
        data = session.session_data or {}
        return data.get("active_project_id") if isinstance(data, dict) else None

    async def get_company_for_group(self, group_id: str) -> Optional[Any]:
        """Return the company id associated with ``group_id`` (or ``None``)."""

        session = await self.whatsapp_repo.get_session_by_group(group_id)
        return getattr(session, "company_id", None) if session is not None else None

    async def set_active_project(self, group_id: str, project_id: Any) -> Any:
        """Set / replace the active project for a group's session."""

        session = await self._get_session_or_raise(group_id)
        data = dict(session.session_data or {})
        data["active_project_id"] = str(project_id)
        return await self.whatsapp_repo.save_session(
            {
                "group_id": group_id,
                "company_id": session.company_id,
                "session_data": data,
            }
        )

    # -- membership ---------------------------------------------------------
    async def verify_group_membership(
        self, group_id: str, phone_number: str
    ) -> bool:
        """Return True if ``phone_number`` is a member of ``group_id``.

        Uses the cached member list in the session first; if the group is
        unknown or the cache is empty it falls back to a live lookup.
        """

        normalised = _normalise_number(phone_number)
        session = await self.whatsapp_repo.get_session_by_group(group_id)
        members: list[str] = []
        if session is not None and isinstance(session.session_data, dict):
            members = [
                _normalise_number(m)
                for m in session.session_data.get("members", [])
            ]
        if not members:
            members = [
                _normalise_number(m) for m in await self._fetch_member_numbers(group_id)
            ]
        return normalised in members

    async def sync_group_members(self, group_id: str) -> list[str]:
        """Refresh the cached member list from the live WATI API.

        Returns the list of member phone numbers and persists it in the
        session's ``session_data``.
        """

        numbers = await self._fetch_member_numbers(group_id)
        session = await self.whatsapp_repo.get_session_by_group(group_id)
        if session is not None:
            data = dict(session.session_data or {})
            data["members"] = numbers
            await self.whatsapp_repo.save_session(
                {
                    "group_id": group_id,
                    "company_id": session.company_id,
                    "session_data": data,
                }
            )
        _log.info("Synced %d members for group %s", len(numbers), group_id)
        return numbers

    async def _fetch_member_numbers(self, group_id: str) -> list[str]:
        members = await self.client.get_group_members(group_id)
        numbers: list[str] = []
        for member in members:
            if isinstance(member, dict):
                num = (
                    member.get("phone")
                    or member.get("phoneNumber")
                    or member.get("waId")
                    or member.get("number")
                )
                if num:
                    numbers.append(str(num))
            elif member:
                numbers.append(str(member))
        return numbers

    # -- lifecycle ----------------------------------------------------------
    async def validate_group(self, group_id: str) -> bool:
        """Return True if a group has an active, registered session."""

        session = await self.whatsapp_repo.get_session_by_group(group_id)
        if session is None:
            return False
        return bool(getattr(session, "is_active", False))


def _normalise_number(number: Any) -> str:
    """Normalise a phone number for comparison (strip spaces / punctuation)."""

    text = str(number or "").strip()
    return "".join(ch for ch in text if ch.isdigit() or ch == "+")


__all__ = ["SessionManager"]
