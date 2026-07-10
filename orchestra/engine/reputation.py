"""Contractor reputation — the compounding performance ledger.

Every time a team finishes a task, we record *one* structured outcome (was it
on time? by how much? estimated vs. actual duration). Those outcomes accumulate
per team, across projects and openings, into a **reputation score** the engine
can use to rank teams for new work. The more the platform is used, the sharper
the scores get — this is the data asset competitors cannot copy.

This module is deliberately split into two layers:

* **Pure scoring** (:class:`TaskOutcome`, :func:`outcome_from_task`,
  :func:`reputation_score`) — no I/O, no database, fully deterministic and unit
  testable. Mirrors the pure style of :mod:`orchestra.engine.state_machine` and
  the confidence maths in :mod:`orchestra.engine.workflow_engine`.
* **Persistence** (:class:`ReputationTracker`) — an async wrapper that records
  outcomes into the existing ``learning_data`` table (``observation_type =
  "task_outcome"``) and reads them back to compute scores.

Design choices that keep the score honest:

* **Cold-start safe** — a brand-new team with no history scores at the neutral
  prior (:data:`NEUTRAL_SCORE`) with zero confidence, so it is neither punished
  nor artificially boosted.
* **Gaming resistant** — the score is shrunk toward the prior by
  :data:`PRIOR_WEIGHT` pseudo-observations, so a team cannot spike its rating
  with a handful of easy wins; a real track record is required to move it.
* **Optional recency weighting** — pass ``half_life_days`` to decay stale
  outcomes so a team that has improved (or slipped) is judged on recent work.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional, Sequence

from ..services.config import get_logger

_log = get_logger(__name__)

# A team with no history is assumed "decent but unproven": high enough not to
# block new contractors, low enough that a proven on-time team out-ranks them.
NEUTRAL_SCORE: float = 0.7

# Pseudo-observations at the prior. The reputation of a team with ``n`` real
# outcomes is pulled ``PRIOR_WEIGHT / (PRIOR_WEIGHT + n)`` of the way back to
# NEUTRAL_SCORE — so ~3 outcomes are needed before the score really moves.
PRIOR_WEIGHT: float = 3.0

# How strongly reputation nudges the team-assignment ranking. Kept small so
# task/skill fit stays dominant and reputation acts as a tie-breaker.
REPUTATION_BLEND: float = 0.15

_OBSERVATION_TYPE = "task_outcome"


# ---------------------------------------------------------------------------
# Pure scoring
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TaskOutcome:
    """One completed-task performance record attributed to a team."""

    team_id: Optional[str] = None
    on_time: bool = True
    delay_days: int = 0
    estimated_days: Optional[int] = None
    actual_days: Optional[int] = None
    task_type: Optional[str] = None
    location: Optional[str] = None
    task_id: Optional[str] = None
    at: Optional[str] = None  # ISO-8601 completion timestamp

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict for storage in ``learning_data``."""

        return asdict(self)

    @classmethod
    def from_content(cls, content: dict[str, Any]) -> "TaskOutcome":
        """Rebuild an outcome from a stored ``learning_data.content`` dict."""

        return cls(
            team_id=_opt_str(content.get("team_id")),
            on_time=bool(content.get("on_time", True)),
            delay_days=int(content.get("delay_days") or 0),
            estimated_days=_opt_int(content.get("estimated_days")),
            actual_days=_opt_int(content.get("actual_days")),
            task_type=content.get("task_type"),
            location=content.get("location"),
            task_id=_opt_str(content.get("task_id")),
            at=content.get("at"),
        )


def outcome_from_task(
    task: Any,
    *,
    project: Any = None,
    now: Optional[datetime] = None,
) -> Optional[TaskOutcome]:
    """Derive a :class:`TaskOutcome` from a completed task.

    Returns ``None`` when the task cannot be scored — i.e. it has no owning team
    (nothing to attribute the outcome to) or no deadline (nothing to judge
    on-time against). Recording only judgeable outcomes keeps the ledger honest.

    Args:
        task: A task record (ORM model or any object exposing ``team_id``,
            ``deadline``, ``completed_at`` and ``created_at`` attributes).
        project: Optional owning project, used to tag the outcome's location.
        now: Override for the current time (falls back to ``completed_at`` or
            the real clock); primarily for deterministic tests.
    """

    team_id = _opt_str(getattr(task, "team_id", None))
    if team_id is None:
        return None

    deadline = _as_date(getattr(task, "deadline", None))
    if deadline is None:
        return None

    completed_dt = _as_datetime(getattr(task, "completed_at", None)) or now
    completed_date = _as_date(completed_dt) or _as_date(now) or datetime.now(
        timezone.utc
    ).date()

    created_date = _as_date(getattr(task, "created_at", None))

    delay = (completed_date - deadline).days
    on_time = delay <= 0

    estimated_days: Optional[int] = None
    actual_days: Optional[int] = None
    if created_date is not None:
        est = (deadline - created_date).days
        act = (completed_date - created_date).days
        estimated_days = est if est >= 0 else None
        actual_days = act if act >= 0 else None

    metadata = getattr(task, "metadata_", None) or {}
    task_type = None
    if isinstance(metadata, dict):
        task_type = metadata.get("task_type")
    task_type = task_type or getattr(task, "title", None)

    location = getattr(project, "location", None)
    if location is None and isinstance(metadata, dict):
        location = metadata.get("location")

    at = None
    if isinstance(completed_dt, datetime):
        at = completed_dt.isoformat()

    return TaskOutcome(
        team_id=team_id,
        on_time=on_time,
        delay_days=max(0, delay),
        estimated_days=estimated_days,
        actual_days=actual_days,
        task_type=task_type,
        location=location,
        task_id=_opt_str(getattr(task, "id", None)),
        at=at,
    )


def reputation_score(
    outcomes: Sequence[TaskOutcome],
    *,
    prior: float = NEUTRAL_SCORE,
    prior_weight: float = PRIOR_WEIGHT,
    half_life_days: Optional[float] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Compute a confidence-weighted reputation score from raw outcomes.

    The score is the on-time rate shrunk toward ``prior`` by ``prior_weight``
    pseudo-observations (a Bayesian/Beta-style smoothing):

        score = (prior * prior_weight + Σ wᵢ · onTimeᵢ) / (prior_weight + Σ wᵢ)

    With no outcomes this returns exactly ``prior`` at zero confidence.

    Args:
        outcomes: The team's recorded task outcomes.
        prior: Neutral score assumed for an unproven team.
        prior_weight: Strength of the prior, in pseudo-observations.
        half_life_days: When set, older outcomes are exponentially down-weighted
            with this half-life (requires each outcome's ``at`` timestamp).
        now: Reference "now" for recency weighting (defaults to the real clock).

    Returns:
        A dict with ``score``, ``confidence`` (0-1, grows with sample size),
        ``sample_size``, ``on_time_rate`` (``None`` when no data) and
        ``avg_delay_days``.
    """

    reference = now or datetime.now(timezone.utc)
    weighted_on_time = 0.0
    total_weight = 0.0
    delays: list[int] = []

    for outcome in outcomes:
        weight = _recency_weight(outcome, half_life_days, reference)
        total_weight += weight
        if outcome.on_time:
            weighted_on_time += weight
        delays.append(max(0, int(outcome.delay_days)))

    denom = prior_weight + total_weight
    score = (prior * prior_weight + weighted_on_time) / denom if denom else prior
    confidence = total_weight / denom if denom else 0.0
    on_time_rate = (weighted_on_time / total_weight) if total_weight else None

    return {
        "score": round(_clamp(score), 3),
        "confidence": round(_clamp(confidence), 3),
        "sample_size": len(outcomes),
        "on_time_rate": round(on_time_rate, 3) if on_time_rate is not None else None,
        "avg_delay_days": round(sum(delays) / len(delays), 2) if delays else 0.0,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
class ReputationTracker:
    """Records and reads task outcomes via the ``learning_data`` store.

    Outcomes live under ``observation_type = "task_outcome"`` so they reuse the
    existing multi-tenant, RLS-protected learning table. A dedicated
    ``task_outcomes`` table (indexed by team/type/location) is the recommended
    next step once reputation-driven analytics grow — the pure scoring above is
    storage-agnostic, so that migration would not touch the maths.
    """

    OBSERVATION_TYPE = _OBSERVATION_TYPE

    def __init__(self, learning_repo: Any = None) -> None:
        self._learning_repo = learning_repo

    @property
    def learning_repo(self) -> Any:
        if self._learning_repo is None:
            from ..database.repositories import LearningRepository

            self._learning_repo = LearningRepository()
        return self._learning_repo

    async def record_outcome(
        self,
        outcome: TaskOutcome,
        *,
        company_id: Optional[Any] = None,
        session: Any = None,
    ) -> Any:
        """Persist one task outcome as a learning observation."""

        _log.info(
            "Recording task outcome team=%s on_time=%s delay=%dd",
            outcome.team_id,
            outcome.on_time,
            outcome.delay_days,
        )
        return await self.learning_repo.save_observation(
            {
                "company_id": company_id,
                "observation_type": self.OBSERVATION_TYPE,
                "content": outcome.as_dict(),
                "confidence": 1.0 if outcome.on_time else 0.0,
            },
            session=session,
        )

    async def get_team_reputation(
        self,
        team_id: Any,
        *,
        company_id: Optional[Any] = None,
        half_life_days: Optional[float] = None,
    ) -> dict[str, Any]:
        """Return the full reputation bundle for a single team."""

        outcomes = await self._load_outcomes(company_id=company_id, team_id=team_id)
        bundle = reputation_score(outcomes, half_life_days=half_life_days)
        bundle["team_id"] = str(team_id)
        return bundle

    async def get_reputations(
        self,
        team_ids: Iterable[Any],
        *,
        company_id: Optional[Any] = None,
        half_life_days: Optional[float] = None,
    ) -> dict[str, float]:
        """Return a ``{team_id: score}`` map for several teams in one read."""

        outcomes = await self._load_outcomes(company_id=company_id)
        by_team: dict[str, list[TaskOutcome]] = {}
        for outcome in outcomes:
            if outcome.team_id is None:
                continue
            by_team.setdefault(str(outcome.team_id), []).append(outcome)
        return {
            str(team_id): reputation_score(
                by_team.get(str(team_id), []), half_life_days=half_life_days
            )["score"]
            for team_id in team_ids
        }

    async def _load_outcomes(
        self,
        *,
        company_id: Optional[Any] = None,
        team_id: Optional[Any] = None,
    ) -> list[TaskOutcome]:
        rows = await self.learning_repo.get_learning_data(
            company_id, observation_type=self.OBSERVATION_TYPE
        )
        outcomes: list[TaskOutcome] = []
        for row in rows:
            content = getattr(row, "content", None) or {}
            if not isinstance(content, dict):
                continue
            if team_id is not None and str(content.get("team_id")) != str(team_id):
                continue
            outcomes.append(TaskOutcome.from_content(content))
        return outcomes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _recency_weight(
    outcome: TaskOutcome,
    half_life_days: Optional[float],
    reference: datetime,
) -> float:
    if not half_life_days or half_life_days <= 0 or not outcome.at:
        return 1.0
    stamped = _parse_iso(outcome.at)
    if stamped is None:
        return 1.0
    age_days = max(0.0, (reference - stamped).total_seconds() / 86_400.0)
    return 0.5 ** (age_days / half_life_days)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _opt_str(value: Any) -> Optional[str]:
    return None if value is None else str(value)


def _opt_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    return None


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = [
    "NEUTRAL_SCORE",
    "PRIOR_WEIGHT",
    "REPUTATION_BLEND",
    "TaskOutcome",
    "outcome_from_task",
    "reputation_score",
    "ReputationTracker",
]
