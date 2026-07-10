"""Unit tests for :mod:`orchestra.engine.reputation`.

The scoring maths and outcome derivation are pure and tested directly. The
:class:`ReputationTracker` and the assignment blend are exercised against the
in-memory fakes from :mod:`tests.fixtures.sample_data` — no database required.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from tests.fixtures.sample_data import FakeLearningRepo, InMemoryState, new_id

from orchestra.engine.reputation import (
    NEUTRAL_SCORE,
    ReputationTracker,
    TaskOutcome,
    outcome_from_task,
    reputation_score,
)
from orchestra.engine.task_manager import TaskManager


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


# ===========================================================================
# Pure scoring
# ===========================================================================
class ReputationScoreTests(unittest.TestCase):
    def test_no_history_returns_neutral_prior_at_zero_confidence(self):
        result = reputation_score([])
        self.assertEqual(result["score"], NEUTRAL_SCORE)
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["sample_size"], 0)
        self.assertIsNone(result["on_time_rate"])
        self.assertEqual(result["avg_delay_days"], 0.0)

    def test_on_time_history_scores_above_prior(self):
        outcomes = [TaskOutcome(team_id="t", on_time=True) for _ in range(3)]
        result = reputation_score(outcomes)
        # (0.7*3 + 3) / (3 + 3) = 0.85
        self.assertAlmostEqual(result["score"], 0.85, places=3)
        self.assertEqual(result["on_time_rate"], 1.0)

    def test_late_history_scores_below_prior(self):
        outcomes = [TaskOutcome(team_id="t", on_time=False, delay_days=2) for _ in range(3)]
        result = reputation_score(outcomes)
        self.assertLess(result["score"], NEUTRAL_SCORE)
        self.assertEqual(result["on_time_rate"], 0.0)
        self.assertEqual(result["avg_delay_days"], 2.0)

    def test_confidence_grows_with_sample_size(self):
        few = reputation_score([TaskOutcome(team_id="t", on_time=True)])
        many = reputation_score([TaskOutcome(team_id="t", on_time=True) for _ in range(20)])
        self.assertLess(few["confidence"], many["confidence"])
        # A long clean record should approach (but not exceed) a perfect score.
        self.assertGreater(many["score"], 0.9)
        self.assertLessEqual(many["score"], 1.0)

    def test_gaming_resistance_two_wins_cannot_spike_the_score(self):
        # Two easy on-time wins are shrunk toward the prior, not a 1.0 rating.
        result = reputation_score([TaskOutcome(team_id="t", on_time=True) for _ in range(2)])
        self.assertLess(result["score"], 0.9)

    def test_recency_weighting_favours_recent_outcomes(self):
        outcomes = [
            TaskOutcome(team_id="t", on_time=True, at="2024-06-01T00:00:00+00:00"),
            TaskOutcome(team_id="t", on_time=False, delay_days=5, at="2024-01-01T00:00:00+00:00"),
        ]
        now = _utc(2024, 6, 2)
        flat = reputation_score(outcomes, now=now)
        decayed = reputation_score(outcomes, half_life_days=30, now=now)
        # Decaying the stale late outcome lifts the score toward the recent win.
        self.assertGreater(decayed["score"], flat["score"])


# ===========================================================================
# Outcome derivation
# ===========================================================================
class OutcomeFromTaskTests(unittest.TestCase):
    def _task(self, **kw):
        base = dict(
            id=new_id(),
            team_id="team-1",
            project_id="proj-1",
            title="Install POS",
            deadline=date(2024, 1, 10),
            completed_at=_utc(2024, 1, 8),
            created_at=_utc(2024, 1, 1),
            metadata_={},
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def test_unassigned_task_is_not_scored(self):
        self.assertIsNone(outcome_from_task(self._task(team_id=None)))

    def test_task_without_deadline_is_not_scored(self):
        self.assertIsNone(outcome_from_task(self._task(deadline=None)))

    def test_on_time_completion(self):
        outcome = outcome_from_task(self._task())
        assert outcome is not None
        self.assertTrue(outcome.on_time)
        self.assertEqual(outcome.delay_days, 0)
        self.assertEqual(outcome.estimated_days, 9)
        self.assertEqual(outcome.actual_days, 7)

    def test_late_completion_records_delay(self):
        outcome = outcome_from_task(self._task(completed_at=_utc(2024, 1, 13)))
        assert outcome is not None
        self.assertFalse(outcome.on_time)
        self.assertEqual(outcome.delay_days, 3)

    def test_location_is_taken_from_project(self):
        project = SimpleNamespace(location="Riyadh", company_id="c1")
        outcome = outcome_from_task(self._task(), project=project)
        assert outcome is not None
        self.assertEqual(outcome.location, "Riyadh")

    def test_round_trips_through_content_dict(self):
        outcome = outcome_from_task(self._task())
        assert outcome is not None
        self.assertEqual(TaskOutcome.from_content(outcome.as_dict()), outcome)


# ===========================================================================
# Persistence
# ===========================================================================
class ReputationTrackerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = InMemoryState()
        self.tracker = ReputationTracker(learning_repo=FakeLearningRepo(self.state))

    async def test_record_and_read_back_team_reputation(self):
        for _ in range(3):
            await self.tracker.record_outcome(
                TaskOutcome(team_id="team-a", on_time=True), company_id="c1"
            )
        bundle = await self.tracker.get_team_reputation("team-a", company_id="c1")
        self.assertEqual(bundle["sample_size"], 3)
        self.assertEqual(bundle["on_time_rate"], 1.0)
        self.assertEqual(bundle["team_id"], "team-a")

    async def test_get_reputations_maps_teams_and_defaults_unknown_to_neutral(self):
        await self.tracker.record_outcome(
            TaskOutcome(team_id="team-a", on_time=True), company_id="c1"
        )
        await self.tracker.record_outcome(
            TaskOutcome(team_id="team-b", on_time=False, delay_days=4), company_id="c1"
        )
        reps = await self.tracker.get_reputations(
            ["team-a", "team-b", "team-unknown"], company_id="c1"
        )
        self.assertGreater(reps["team-a"], reps["team-b"])
        self.assertEqual(reps["team-unknown"], NEUTRAL_SCORE)

    async def test_reputations_are_scoped_by_company(self):
        await self.tracker.record_outcome(
            TaskOutcome(team_id="team-a", on_time=False, delay_days=9), company_id="other"
        )
        bundle = await self.tracker.get_team_reputation("team-a", company_id="c1")
        # The other tenant's outcome must not bleed into this company's score.
        self.assertEqual(bundle["sample_size"], 0)
        self.assertEqual(bundle["score"], NEUTRAL_SCORE)


# ===========================================================================
# Assignment blend
# ===========================================================================
class _FakeTeamRepo:
    def __init__(self, teams):
        self._teams = teams

    async def list(self, **filters):
        return list(self._teams)


class _RaisingEmbeddings:
    """Forces the keyword-overlap fallback so fit scores are deterministic."""

    def generate_embedding(self, *_a, **_k):
        raise RuntimeError("embeddings disabled for test")


class _FakeReputation:
    def __init__(self, scores):
        self.scores = scores

    async def get_reputations(self, team_ids, *, company_id=None):
        return {str(t): self.scores.get(str(t), NEUTRAL_SCORE) for t in team_ids}


class AutoAssignReputationBlendTests(unittest.IsolatedAsyncioTestCase):
    def _teams(self):
        # Identical name → identical keyword fit; only reputation differs.
        return [
            SimpleNamespace(id="lo", name="deploy pos network"),
            SimpleNamespace(id="hi", name="deploy pos network"),
        ]

    async def test_without_reputation_fit_tie_breaks_to_first(self):
        manager = TaskManager(
            team_repo=_FakeTeamRepo(self._teams()),
            embeddings_service=_RaisingEmbeddings(),
        )
        best = await manager.auto_assign_task("deploy pos network")
        self.assertEqual(best.id, "lo")

    async def test_reputation_flips_an_otherwise_tied_assignment(self):
        manager = TaskManager(
            team_repo=_FakeTeamRepo(self._teams()),
            embeddings_service=_RaisingEmbeddings(),
            reputation=_FakeReputation({"lo": 0.4, "hi": 0.95}),
        )
        best = await manager.auto_assign_task("deploy pos network")
        self.assertEqual(best.id, "hi")

    async def test_reputation_lookup_failure_degrades_to_fit(self):
        class _Boom:
            async def get_reputations(self, *_a, **_k):
                raise RuntimeError("db down")

        manager = TaskManager(
            team_repo=_FakeTeamRepo(self._teams()),
            embeddings_service=_RaisingEmbeddings(),
            reputation=_Boom(),
        )
        best = await manager.auto_assign_task("deploy pos network")
        self.assertEqual(best.id, "lo")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
