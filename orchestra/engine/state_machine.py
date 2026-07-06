"""Universal state machine for ANY learned workflow.

:class:`StateMachine` operates on a normalised workflow definition — an ordered
list of stages, each with dependencies and a status — and answers the questions
the orchestrator needs to coordinate a project:

    * What stage should happen next?
    * Is a given transition allowed?
    * How far along is the project?
    * What is blocking progress?
    * Which stages are delayed, and how is work distributed across teams?

It is deliberately **workflow-agnostic**: it makes no assumptions about the
domain (retail, construction, events, ...). It accepts either a plain workflow
dict (``{"stages": [...]}``), a :class:`~orchestra.database.models.Workflow`-like
object with a ``stages`` attribute, or a list of
:class:`~orchestra.database.models.ProjectStage`-like objects/dicts.

The machine performs **pure, synchronous computation** (no I/O), which keeps it
trivially testable; the async orchestration layer persists any resulting state
changes through the repositories.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from .exceptions import StateTransitionError, WorkflowError

# Stage statuses that count as "finished" for dependency-satisfaction and
# progress purposes.
_DONE_STATUSES = frozenset({"completed", "done", "skipped"})
_ACTIVE_STATUS = "in_progress"
_BLOCKED_STATUS = "blocked"
_PENDING_STATUS = "pending"


def _now() -> datetime:
    """Return an aware UTC ``datetime`` (single choke-point for testability)."""

    return datetime.now(timezone.utc)


def _to_datetime(value: Any) -> Optional[datetime]:
    """Best-effort coercion of ``value`` into an aware UTC ``datetime``."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


class StateMachine:
    """A dependency-aware state machine over a workflow's stages."""

    def __init__(self, workflow: Any) -> None:
        """Initialise from a workflow definition.

        Args:
            workflow: One of

                * a dict like ``{"name": .., "stages": [{...}, ...]}``,
                * an object exposing a ``stages`` attribute, or
                * a raw list of stage dicts / stage objects.

            Each stage may provide ``id``/``stage_id``/``name``,
            ``depends_on`` (list of stage ids or names), ``status``,
            ``team_id``, ``sequence``, ``deadline``, ``started_at`` and
            ``completed_at``.

        Raises:
            WorkflowError: If no stages can be derived from ``workflow``.
        """

        self.workflow = workflow
        self.stages: list[dict[str, Any]] = self._normalise_stages(workflow)
        if not self.stages:
            raise WorkflowError("Cannot build a state machine from an empty workflow")
        # Fast lookups by canonical id and by name (case-insensitive).
        self._by_id: dict[str, dict[str, Any]] = {s["id"]: s for s in self.stages}
        self._by_name: dict[str, dict[str, Any]] = {
            s["name"].strip().lower(): s for s in self.stages if s.get("name")
        }

    # -- normalisation ------------------------------------------------------
    @staticmethod
    def _extract_raw_stages(workflow: Any) -> Iterable[Any]:
        if workflow is None:
            return []
        if isinstance(workflow, (list, tuple)):
            return list(workflow)
        if isinstance(workflow, dict):
            return workflow.get("stages") or []
        stages = getattr(workflow, "stages", None)
        return list(stages) if stages else []

    def _normalise_stages(self, workflow: Any) -> list[dict[str, Any]]:
        """Turn heterogeneous stage inputs into uniform dicts."""

        normalised: list[dict[str, Any]] = []
        for index, raw in enumerate(self._extract_raw_stages(workflow)):
            stage = self._normalise_one(raw, index)
            if stage is not None:
                normalised.append(stage)
        # Stable ordering by sequence, then original order.
        normalised.sort(key=lambda s: (s["sequence"], s["_order"]))
        return normalised

    @staticmethod
    def _get(raw: Any, *keys: str, default: Any = None) -> Any:
        """Fetch the first present attribute/key from ``raw``."""

        for key in keys:
            if isinstance(raw, dict):
                if key in raw and raw[key] is not None:
                    return raw[key]
            else:
                value = getattr(raw, key, None)
                if value is not None:
                    return value
        return default

    def _normalise_one(self, raw: Any, index: int) -> Optional[dict[str, Any]]:
        name = self._get(raw, "name", "title", default=None)
        raw_id = self._get(raw, "id", "stage_id", default=None)
        identifier = str(raw_id) if raw_id is not None else (
            str(name) if name else f"stage_{index}"
        )
        status = self._get(raw, "status", default=_PENDING_STATUS)
        # SQLAlchemy enums expose ``.value``; normalise to a plain lowercase str.
        status = getattr(status, "value", status)
        status = str(status).lower()
        depends_on = self._get(raw, "depends_on", "dependencies", default=[]) or []
        if not isinstance(depends_on, (list, tuple)):
            depends_on = [depends_on]
        team_id = self._get(raw, "team_id", "team", "owner", default=None)
        sequence = self._get(raw, "sequence", "order", default=index)
        try:
            sequence = int(sequence)
        except (TypeError, ValueError):
            sequence = index
        return {
            "id": identifier,
            "name": str(name) if name else identifier,
            "status": status,
            "depends_on": [str(d) for d in depends_on],
            "team_id": str(team_id) if team_id is not None else None,
            "sequence": sequence,
            "deadline": self._get(raw, "deadline", "due_date", default=None),
            "started_at": self._get(raw, "started_at", default=None),
            "completed_at": self._get(raw, "completed_at", default=None),
            "_order": index,
        }

    # -- lookups ------------------------------------------------------------
    def _resolve(self, stage_id: str) -> Optional[dict[str, Any]]:
        """Resolve a stage by id or (case-insensitive) name."""

        if stage_id is None:
            return None
        key = str(stage_id)
        if key in self._by_id:
            return self._by_id[key]
        return self._by_name.get(key.strip().lower())

    def _dependencies_met(self, stage: dict[str, Any]) -> bool:
        for dep in stage["depends_on"]:
            dep_stage = self._resolve(dep)
            if dep_stage is None:
                # Unknown dependency — treat as unmet (validate_workflow flags it).
                return False
            if dep_stage["status"] not in _DONE_STATUSES:
                return False
        return True

    # -- public API ---------------------------------------------------------
    def get_next_stage(self) -> Optional[dict[str, Any]]:
        """Return the next actionable stage, or ``None`` if none is ready.

        The next stage is the lowest-sequence stage that is still ``pending``
        and whose dependencies are all satisfied. An already ``in_progress``
        stage is returned in preference, since it is the current focus.
        """

        for stage in self.stages:
            if stage["status"] == _ACTIVE_STATUS:
                return stage
        for stage in self.stages:
            if stage["status"] == _PENDING_STATUS and self._dependencies_met(stage):
                return stage
        return None

    def can_transition_to(self, stage_id: str) -> bool:
        """Return ``True`` if the machine may transition to ``stage_id``."""

        stage = self._resolve(stage_id)
        if stage is None:
            return False
        if stage["status"] in _DONE_STATUSES:
            return False
        return self._dependencies_met(stage)

    def transition_to(self, stage_id: str) -> dict[str, Any]:
        """Move ``stage_id`` into progress and return the updated stage.

        Args:
            stage_id: The id or name of the stage to activate.

        Returns:
            The stage dict, now marked ``in_progress``.

        Raises:
            StateTransitionError: If the stage is unknown, already finished, or
                has unsatisfied dependencies.
        """

        stage = self._resolve(stage_id)
        if stage is None:
            raise StateTransitionError(
                f"Unknown stage {stage_id!r}", stage_id=str(stage_id), reason="not_found"
            )
        if stage["status"] in _DONE_STATUSES:
            raise StateTransitionError(
                f"Stage {stage['name']!r} is already {stage['status']}",
                stage_id=stage["id"],
                reason="already_finished",
            )
        if not self._dependencies_met(stage):
            unmet = [
                d
                for d in stage["depends_on"]
                if (dep := self._resolve(d)) is None
                or dep["status"] not in _DONE_STATUSES
            ]
            raise StateTransitionError(
                f"Stage {stage['name']!r} has unmet dependencies: {unmet}",
                stage_id=stage["id"],
                reason="unmet_dependencies",
            )
        stage["status"] = _ACTIVE_STATUS
        if not stage.get("started_at"):
            stage["started_at"] = _now()
        return stage

    def complete_stage(self, stage_id: str) -> dict[str, Any]:
        """Mark ``stage_id`` completed and return it.

        Raises:
            StateTransitionError: If the stage is unknown.
        """

        stage = self._resolve(stage_id)
        if stage is None:
            raise StateTransitionError(
                f"Unknown stage {stage_id!r}", stage_id=str(stage_id), reason="not_found"
            )
        stage["status"] = "completed"
        stage["completed_at"] = _now()
        return stage

    def get_progress(self) -> float:
        """Return overall completion as a percentage (0-100, one decimal)."""

        total = len(self.stages)
        if total == 0:
            return 0.0
        done = sum(1 for s in self.stages if s["status"] in _DONE_STATUSES)
        return round(done / total * 100, 1)

    def get_blockers(self) -> list[dict[str, Any]]:
        """Identify stages that block forward progress.

        A blocker is any stage explicitly marked ``blocked``, or a ``pending``
        stage whose dependencies are not (yet) satisfied. Each entry records the
        blocking reason and the specific unmet dependencies.
        """

        blockers: list[dict[str, Any]] = []
        for stage in self.stages:
            if stage["status"] == _BLOCKED_STATUS:
                blockers.append(
                    {
                        "stage_id": stage["id"],
                        "name": stage["name"],
                        "reason": "explicitly_blocked",
                        "unmet_dependencies": [],
                    }
                )
                continue
            if stage["status"] == _PENDING_STATUS and not self._dependencies_met(stage):
                unmet = [
                    d
                    for d in stage["depends_on"]
                    if (dep := self._resolve(d)) is None
                    or dep["status"] not in _DONE_STATUSES
                ]
                blockers.append(
                    {
                        "stage_id": stage["id"],
                        "name": stage["name"],
                        "reason": "waiting_on_dependencies",
                        "unmet_dependencies": unmet,
                    }
                )
        return blockers

    def get_delays(self) -> list[dict[str, Any]]:
        """Return per-stage delay information, in days.

        For each stage with a ``deadline``:

            * completed stages report ``completed_at - deadline`` (negative when
              early, positive when late);
            * unfinished stages report ``now - deadline`` when overdue.

        Only stages that are late (or completed late) are returned.
        """

        now = _now()
        delays: list[dict[str, Any]] = []
        for stage in self.stages:
            deadline = _to_datetime(stage.get("deadline"))
            if deadline is None:
                continue
            if stage["status"] in _DONE_STATUSES:
                completed = _to_datetime(stage.get("completed_at"))
                if completed is None:
                    continue
                delay_days = (completed - deadline).days
                if delay_days > 0:
                    delays.append(
                        {
                            "stage_id": stage["id"],
                            "name": stage["name"],
                            "delay_days": delay_days,
                            "status": stage["status"],
                        }
                    )
            else:
                delay_days = (now - deadline).days
                if delay_days > 0:
                    delays.append(
                        {
                            "stage_id": stage["id"],
                            "name": stage["name"],
                            "delay_days": delay_days,
                            "status": stage["status"],
                        }
                    )
        return delays

    def get_team_workload(self) -> dict[str, dict[str, int]]:
        """Return workload per team as ``{team_id: {status_bucket: count}}``.

        Buckets are ``total``, ``active`` (in-progress), ``pending`` and
        ``done``. Stages without a team are grouped under the ``"unassigned"``
        key.
        """

        workload: dict[str, dict[str, int]] = {}
        for stage in self.stages:
            team = stage["team_id"] or "unassigned"
            bucket = workload.setdefault(
                team, {"total": 0, "active": 0, "pending": 0, "done": 0}
            )
            bucket["total"] += 1
            if stage["status"] == _ACTIVE_STATUS:
                bucket["active"] += 1
            elif stage["status"] in _DONE_STATUSES:
                bucket["done"] += 1
            elif stage["status"] == _PENDING_STATUS:
                bucket["pending"] += 1
        return workload

    def get_status_report(self) -> dict[str, Any]:
        """Return a full, JSON-serialisable status summary of the workflow."""

        next_stage = self.get_next_stage()
        counts: dict[str, int] = {}
        for stage in self.stages:
            counts[stage["status"]] = counts.get(stage["status"], 0) + 1
        current = next(
            (s for s in self.stages if s["status"] == _ACTIVE_STATUS), None
        )
        return {
            "total_stages": len(self.stages),
            "progress_pct": self.get_progress(),
            "status_counts": counts,
            "current_stage": current["name"] if current else None,
            "next_stage": next_stage["name"] if next_stage else None,
            "blockers": self.get_blockers(),
            "delays": self.get_delays(),
            "team_workload": self.get_team_workload(),
            "is_complete": all(s["status"] in _DONE_STATUSES for s in self.stages),
            "stages": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "status": s["status"],
                    "depends_on": s["depends_on"],
                    "team_id": s["team_id"],
                }
                for s in self.stages
            ],
        }


__all__ = ["StateMachine"]
