"""Repository for the :class:`Team` aggregate."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import translate_error
from ..exceptions import NotFoundError
from ..models import Team
from .base import BaseRepository, _coerce_uuid


class TeamRepository(BaseRepository[Team]):
    """Data access for teams and their (JSON) members."""

    model = Team

    def __init__(self) -> None:
        super().__init__(Team)

    async def create_team(
        self,
        data: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> Team:
        """Create a new team from a plain ``data`` dict."""

        self._log.info("Creating team name=%r", data.get("name"))
        return await self.add(Team(**data), session=session)

    async def get_team(
        self,
        team_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Team:
        """Return the team or raise :class:`NotFoundError`."""

        return await self.get_or_raise(team_id, session=session)

    async def update_team(
        self,
        team_id: Any,
        values: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> Team:
        """Update arbitrary team fields."""

        self._log.info("Updating team %s", team_id)
        return await self.update(team_id, values, session=session)

    async def get_team_by_lead(
        self,
        lead_whatsapp: str,
        *,
        company_id: Optional[Any] = None,
        session: Optional[AsyncSession] = None,
    ) -> Optional[Team]:
        """Return the (active) team whose lead has ``lead_whatsapp``."""

        async with self._session(session) as sess:
            try:
                stmt = select(Team).where(
                    Team.lead_whatsapp == lead_whatsapp,
                    Team.is_active.is_(True),
                )
                if company_id is not None:
                    stmt = stmt.where(Team.company_id == _coerce_uuid(company_id))
                result = await sess.execute(stmt.limit(1))
                return result.scalars().first()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def get_team_members(
        self,
        team_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> list[dict[str, Any]]:
        """Return the JSON member list for a team."""

        team = await self.get_or_raise(team_id, session=session)
        return list(team.members or [])

    async def add_member(
        self,
        team_id: Any,
        member: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> Team:
        """Add a member object to the team's JSON member list.

        Members are de-duplicated on ``whatsapp`` when present.
        """

        async with self._session(session) as sess:
            try:
                team = await sess.get(Team, _coerce_uuid(team_id))
                if team is None:
                    raise NotFoundError("Team", team_id)
                members = list(team.members or [])
                identifier = member.get("whatsapp")
                if identifier is not None:
                    members = [m for m in members if m.get("whatsapp") != identifier]
                members.append(member)
                # Reassign (rather than mutate) so SQLAlchemy tracks the change.
                team.members = members
                await sess.flush()
                await sess.refresh(team)
                self._log.info("Added member to team %s", team_id)
                return team
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def remove_member(
        self,
        team_id: Any,
        whatsapp: str,
        *,
        session: Optional[AsyncSession] = None,
    ) -> Team:
        """Remove the member with the given ``whatsapp`` from the team."""

        async with self._session(session) as sess:
            try:
                team = await sess.get(Team, _coerce_uuid(team_id))
                if team is None:
                    raise NotFoundError("Team", team_id)
                team.members = [
                    m for m in (team.members or []) if m.get("whatsapp") != whatsapp
                ]
                await sess.flush()
                await sess.refresh(team)
                self._log.info("Removed member %s from team %s", whatsapp, team_id)
                return team
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc


__all__ = ["TeamRepository"]
