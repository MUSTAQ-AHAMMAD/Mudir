"""Repository for the :class:`LearningData` aggregate (AI learning store)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..connection import translate_error
from ..exceptions import NotFoundError
from ..models import LearningData
from .base import BaseRepository, _coerce_uuid


class LearningRepository(BaseRepository[LearningData]):
    """Data access for AI observations, patterns and suggestions."""

    model = LearningData

    def __init__(self) -> None:
        super().__init__(LearningData)

    async def save_observation(
        self,
        data: dict[str, Any],
        *,
        session: Optional[AsyncSession] = None,
    ) -> LearningData:
        """Persist a new learning observation."""

        self._log.info(
            "Saving observation type=%r", data.get("observation_type")
        )
        return await self.add(LearningData(**data), session=session)

    async def get_learning_data(
        self,
        company_id: Optional[Any] = None,
        *,
        observation_type: Optional[str] = None,
        limit: Optional[int] = None,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[LearningData]:
        """Return learning rows, optionally filtered by company/type."""

        async with self._session(session) as sess:
            try:
                stmt = select(LearningData)
                if company_id is not None:
                    stmt = stmt.where(
                        LearningData.company_id == _coerce_uuid(company_id)
                    )
                if observation_type is not None:
                    stmt = stmt.where(
                        LearningData.observation_type == observation_type
                    )
                stmt = stmt.order_by(LearningData.confidence.desc())
                if limit is not None:
                    stmt = stmt.limit(limit)
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def update_confidence(
        self,
        learning_id: Any,
        confidence: float,
        *,
        session: Optional[AsyncSession] = None,
    ) -> LearningData:
        """Set a learning row's ``confidence`` (clamped to [0, 1])."""

        clamped = max(0.0, min(1.0, float(confidence)))
        self._log.debug("Learning %s confidence=%.3f", learning_id, clamped)
        return await self.update(
            learning_id, {"confidence": clamped}, session=session
        )

    async def get_suggestions(
        self,
        company_id: Optional[Any] = None,
        *,
        min_confidence: float = 0.5,
        include_implemented: bool = False,
        limit: Optional[int] = None,
        session: Optional[AsyncSession] = None,
    ) -> Sequence[LearningData]:
        """Return high-confidence suggestions not yet implemented."""

        async with self._session(session) as sess:
            try:
                stmt = select(LearningData).where(
                    LearningData.suggestion.is_not(None),
                    LearningData.confidence >= min_confidence,
                )
                if not include_implemented:
                    stmt = stmt.where(LearningData.is_implemented.is_(False))
                if company_id is not None:
                    stmt = stmt.where(
                        LearningData.company_id == _coerce_uuid(company_id)
                    )
                stmt = stmt.order_by(LearningData.confidence.desc())
                if limit is not None:
                    stmt = stmt.limit(limit)
                result = await sess.execute(stmt)
                return result.scalars().all()
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc

    async def mark_suggestion_implemented(
        self,
        learning_id: Any,
        *,
        session: Optional[AsyncSession] = None,
    ) -> LearningData:
        """Mark a suggestion implemented, stamping ``implemented_at``."""

        async with self._session(session) as sess:
            try:
                row = await sess.get(LearningData, _coerce_uuid(learning_id))
                if row is None:
                    raise NotFoundError("LearningData", learning_id)
                row.is_implemented = True
                row.implemented_at = datetime.now(timezone.utc)
                await sess.flush()
                await sess.refresh(row)
                self._log.info("Marked suggestion %s implemented", learning_id)
                return row
            except SQLAlchemyError as exc:
                raise translate_error(exc) from exc


__all__ = ["LearningRepository"]
