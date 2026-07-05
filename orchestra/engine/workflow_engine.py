"""Dynamic workflow learning engine.

The :class:`WorkflowEngine` turns free-form conversations into structured,
reusable workflows and continuously improves them. It is the "Strategy Pattern"
seam of the system: workflow learning is delegated to the local LLM
(:mod:`orchestra.services.llm_service`) while validation, merging and confidence
scoring are deterministic, dependency-free computations.

Learned workflows are persisted through
:class:`orchestra.database.repositories.WorkflowRepository` as a list of stage
templates::

    [{"name": .., "description": .., "owner": .., "depends_on": [..]}]

Dependencies are injected for testability; sensible lazy defaults are used when
none are supplied (mirroring the services layer's ``get_service()`` pattern).
"""

from __future__ import annotations

from typing import Any, Optional

from ..services.config import get_logger
from .exceptions import WorkflowError

_log = get_logger(__name__)


class WorkflowEngine:
    """Learn, validate, improve and score dynamic workflows."""

    def __init__(
        self,
        llm_service: Any = None,
        workflow_repo: Any = None,
    ) -> None:
        """Create the engine.

        Args:
            llm_service: An object exposing ``extract_workflow`` / ``chat`` (the
                LLM service). Lazily resolved when omitted.
            workflow_repo: A :class:`WorkflowRepository`-like object. Lazily
                resolved when omitted.
        """

        self._llm = llm_service
        self._workflow_repo = workflow_repo

    # -- lazy dependency accessors -----------------------------------------
    @property
    def llm(self) -> Any:
        if self._llm is None:
            from ..services import llm_service

            self._llm = llm_service.get_service()
        return self._llm

    @property
    def workflow_repo(self) -> Any:
        if self._workflow_repo is None:
            from ..database.repositories import WorkflowRepository

            self._workflow_repo = WorkflowRepository()
        return self._workflow_repo

    # -- learning -----------------------------------------------------------
    async def learn_workflow(
        self, conversation: str, industry: Optional[str] = None
    ) -> dict[str, Any]:
        """Extract a structured workflow from a conversation transcript.

        Args:
            conversation: The raw conversation / brief describing the project.
            industry: Optional industry hint (e.g. ``"retail"``) recorded in the
                learned workflow's metadata and used to name it.

        Returns:
            A workflow dict with ``workflow_name``, ``stages``, ``industry`` and
            a heuristic ``confidence`` score.

        Raises:
            WorkflowError: If no stages could be inferred from the conversation.
        """

        _log.info("Learning workflow (industry=%s)", industry)
        raw = self.llm.extract_workflow(conversation)
        stages = self._clean_stages(raw.get("stages") or [])
        if not stages:
            raise WorkflowError("LLM did not infer any workflow stages")
        name = raw.get("workflow_name") or (
            f"{industry} workflow" if industry else "learned_workflow"
        )
        workflow = {
            "workflow_name": name,
            "industry": industry,
            "stages": stages,
        }
        workflow["confidence"] = self.calculate_confidence(workflow)
        return workflow

    async def extract_stages(self, conversation: str) -> list[dict[str, Any]]:
        """Identify and return just the ordered stages from ``conversation``."""

        raw = self.llm.extract_workflow(conversation)
        return self._clean_stages(raw.get("stages") or [])

    async def improve_workflow(
        self, workflow_id: Any, new_data: dict[str, Any]
    ) -> Any:
        """Refine a stored workflow using newly observed patterns.

        Merges any new stages from ``new_data`` into the existing workflow,
        recomputes confidence, bumps ``usage_count`` and persists the result.

        Args:
            workflow_id: The id of the stored workflow to improve.
            new_data: A workflow-shaped dict (``{"stages": [...]}``) or a dict of
                observed stage patterns to fold in.

        Returns:
            The updated workflow record.

        Raises:
            WorkflowError: If the workflow does not exist or becomes invalid.
        """

        existing = await self.workflow_repo.get_workflow(workflow_id)
        merged = self.merge_workflows(
            {"stages": list(existing.stages or [])},
            {"stages": self._clean_stages(new_data.get("stages") or [])},
        )
        validation = self.validate_workflow(merged)
        if not validation["valid"]:
            raise WorkflowError(
                f"Improved workflow is invalid: {validation['errors']}"
            )
        confidence = self.calculate_confidence(merged)
        updated = await self.workflow_repo.update_workflow(
            workflow_id,
            {"stages": merged["stages"], "confidence": confidence},
        )
        await self.workflow_repo.increment_usage_count(workflow_id)
        _log.info("Improved workflow id=%s (confidence=%.2f)", workflow_id, confidence)
        return updated

    async def auto_suggest_optimizations(
        self, workflow_id: Any, project_history: Optional[list[Any]] = None
    ) -> list[dict[str, Any]]:
        """Suggest improvements for a workflow based on past project history.

        Uses the LLM to reason over the current stages plus a compact summary of
        historical outcomes (delays, blockers), returning a list of structured
        suggestions.
        """

        workflow = await self.workflow_repo.get_workflow(workflow_id)
        history_blurb = self._render_history(project_history or [])
        import json

        prompt = (
            "Current workflow stages (JSON):\n"
            f"{json.dumps(list(workflow.stages or []), ensure_ascii=False)}\n\n"
            f"Historical outcomes:\n{history_blurb}\n\n"
            "Suggest concrete optimisations (reordering, parallelisation, "
            "removing redundant stages, adding missing ones)."
        )
        system = (
            "You optimise project workflows. Respond ONLY with a JSON object: "
            '{"suggestions": [{"type": str, "stage": str|null, "detail": str, '
            '"impact": "low"|"medium"|"high"}]}. Do not add commentary.'
        )
        result = self.llm._chat_json(prompt, system=system)  # noqa: SLF001
        suggestions = result.get("suggestions")
        return suggestions if isinstance(suggestions, list) else []

    # -- pure computations --------------------------------------------------
    def validate_workflow(self, workflow: Any) -> dict[str, Any]:
        """Validate a workflow for cycles and missing dependencies.

        Args:
            workflow: A workflow dict / object with a ``stages`` list.

        Returns:
            ``{"valid": bool, "errors": [str], "warnings": [str]}``. Cyclic and
            missing-dependency problems are reported as errors; empty workflows
            are an error too.
        """

        stages = self._stages_of(workflow)
        errors: list[str] = []
        warnings: list[str] = []
        if not stages:
            return {"valid": False, "errors": ["workflow has no stages"], "warnings": []}

        # Build a name/id -> stage index. Stages are keyed by name (the learned
        # representation) but we also accept ids for robustness.
        keys: dict[str, str] = {}
        for stage in stages:
            key = str(stage.get("name") or stage.get("id") or "")
            if not key:
                errors.append("a stage is missing a name/id")
                continue
            if key.lower() in keys:
                warnings.append(f"duplicate stage name: {key!r}")
            keys[key.lower()] = key

        # Missing dependencies.
        adjacency: dict[str, list[str]] = {}
        for stage in stages:
            key = str(stage.get("name") or stage.get("id") or "").lower()
            deps = stage.get("depends_on") or []
            resolved: list[str] = []
            for dep in deps:
                dep_key = str(dep).lower()
                if dep_key not in keys:
                    errors.append(
                        f"stage {stage.get('name')!r} depends on unknown stage {dep!r}"
                    )
                else:
                    resolved.append(dep_key)
            adjacency[key] = resolved

        # Cycle detection via DFS colouring.
        WHITE, GREY, BLACK = 0, 1, 2
        colour = {k: WHITE for k in adjacency}

        def _visit(node: str, path: list[str]) -> bool:
            colour[node] = GREY
            for neighbour in adjacency.get(node, []):
                if colour.get(neighbour) == GREY:
                    errors.append(
                        "dependency cycle detected: "
                        + " -> ".join(path + [node, neighbour])
                    )
                    return True
                if colour.get(neighbour) == WHITE and _visit(
                    neighbour, path + [node]
                ):
                    return True
            colour[node] = BLACK
            return False

        for node in list(adjacency):
            if colour[node] == WHITE and _visit(node, []):
                break

        return {"valid": not errors, "errors": errors, "warnings": warnings}

    def merge_workflows(self, workflow1: Any, workflow2: Any) -> dict[str, Any]:
        """Combine two similar workflows into one.

        Stages are matched case-insensitively by name. Matching stages have
        their dependency lists unioned; stages unique to ``workflow2`` are
        appended. The relative order of ``workflow1`` is preserved.

        Returns:
            A merged workflow dict ``{"stages": [...]}``.
        """

        merged: list[dict[str, Any]] = []
        index: dict[str, dict[str, Any]] = {}
        for stage in self._stages_of(workflow1) + self._stages_of(workflow2):
            name = str(stage.get("name") or stage.get("id") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in index:
                existing = index[key]
                deps = list(dict.fromkeys(
                    [*existing.get("depends_on", []), *stage.get("depends_on", [])]
                ))
                existing["depends_on"] = deps
                if not existing.get("description") and stage.get("description"):
                    existing["description"] = stage["description"]
            else:
                clone = {
                    "name": name,
                    "description": stage.get("description"),
                    "owner": stage.get("owner"),
                    "depends_on": list(stage.get("depends_on") or []),
                }
                index[key] = clone
                merged.append(clone)
        return {"stages": merged}

    def calculate_confidence(self, workflow: Any) -> float:
        """Score how well-formed / trustworthy a workflow is (0.0 - 1.0).

        The heuristic rewards workflows that are structurally valid, have a
        healthy number of stages, describe their stages, and encode explicit
        dependencies; it penalises validation errors. If the workflow object
        carries a ``usage_count``, repeated successful use nudges the score up.
        """

        stages = self._stages_of(workflow)
        if not stages:
            return 0.0

        validation = self.validate_workflow(workflow)
        if not validation["valid"]:
            return round(max(0.1, 0.3 - 0.05 * len(validation["errors"])), 2)

        score = 0.5
        # Reward a sensible number of stages (3-12 is the sweet spot).
        n = len(stages)
        if 3 <= n <= 12:
            score += 0.2
        elif n > 1:
            score += 0.1
        # Reward described stages.
        described = sum(1 for s in stages if s.get("description"))
        score += 0.15 * (described / n)
        # Reward explicit dependencies (beyond the first stage).
        with_deps = sum(1 for s in stages if s.get("depends_on"))
        if n > 1:
            score += 0.15 * (with_deps / (n - 1))
        # Usage-based bump when the workflow object tracks it.
        usage = getattr(workflow, "usage_count", None)
        if isinstance(usage, int) and usage > 0:
            score += min(0.1, 0.01 * usage)
        return round(min(score, 1.0), 2)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _stages_of(workflow: Any) -> list[dict[str, Any]]:
        if workflow is None:
            return []
        if isinstance(workflow, dict):
            stages = workflow.get("stages") or []
        else:
            stages = getattr(workflow, "stages", None) or []
        return [s for s in stages if isinstance(s, dict)]

    @staticmethod
    def _clean_stages(stages: list[Any]) -> list[dict[str, Any]]:
        """Normalise LLM-provided stages into the canonical template shape."""

        cleaned: list[dict[str, Any]] = []
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            name = stage.get("name") or stage.get("title")
            if not name:
                continue
            depends_on = stage.get("depends_on") or stage.get("dependencies") or []
            if not isinstance(depends_on, (list, tuple)):
                depends_on = [depends_on]
            cleaned.append(
                {
                    "name": str(name).strip(),
                    "description": stage.get("description"),
                    "owner": stage.get("owner"),
                    "depends_on": [str(d) for d in depends_on],
                }
            )
        return cleaned

    @staticmethod
    def _render_history(history: list[Any]) -> str:
        if not history:
            return "(no historical data available)"
        lines: list[str] = []
        for item in history[:20]:
            lines.append(str(item))
        return "\n".join(lines)


# -- module-level singleton + functional wrappers --------------------------
_default_engine: Optional[WorkflowEngine] = None


def get_engine() -> WorkflowEngine:
    """Return a lazily-instantiated shared :class:`WorkflowEngine`."""

    global _default_engine
    if _default_engine is None:
        _default_engine = WorkflowEngine()
    return _default_engine


async def learn_workflow(
    conversation: str, industry: Optional[str] = None
) -> dict[str, Any]:
    """Module-level wrapper around :meth:`WorkflowEngine.learn_workflow`."""

    return await get_engine().learn_workflow(conversation, industry)


async def extract_stages(conversation: str) -> list[dict[str, Any]]:
    """Module-level wrapper around :meth:`WorkflowEngine.extract_stages`."""

    return await get_engine().extract_stages(conversation)


def validate_workflow(workflow: Any) -> dict[str, Any]:
    """Module-level wrapper around :meth:`WorkflowEngine.validate_workflow`."""

    return get_engine().validate_workflow(workflow)


def merge_workflows(workflow1: Any, workflow2: Any) -> dict[str, Any]:
    """Module-level wrapper around :meth:`WorkflowEngine.merge_workflows`."""

    return get_engine().merge_workflows(workflow1, workflow2)


def calculate_confidence(workflow: Any) -> float:
    """Module-level wrapper around :meth:`WorkflowEngine.calculate_confidence`."""

    return get_engine().calculate_confidence(workflow)


__all__ = [
    "WorkflowEngine",
    "get_engine",
    "learn_workflow",
    "extract_stages",
    "validate_workflow",
    "merge_workflows",
    "calculate_confidence",
]
