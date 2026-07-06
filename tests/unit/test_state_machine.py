"""Unit tests for :class:`orchestra.engine.state_machine.StateMachine`.

The state machine is pure, synchronous computation, so these tests exercise it
directly with plain stage dicts. Covered: normalisation, state transitions,
dependency validation, progress calculation, blocker detection, delay/workload
calculation and status-report generation.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from orchestra.engine.exceptions import StateTransitionError, WorkflowError
from orchestra.engine.state_machine import StateMachine


def _stages():
    """A small linear workflow: A -> B -> C."""

    return [
        {"id": "a", "name": "A", "status": "pending", "sequence": 0, "depends_on": []},
        {"id": "b", "name": "B", "status": "pending", "sequence": 1, "depends_on": ["a"]},
        {"id": "c", "name": "C", "status": "pending", "sequence": 2, "depends_on": ["b"]},
    ]


class ConstructionTests(unittest.TestCase):
    def test_accepts_list_of_dicts(self):
        machine = StateMachine(_stages())
        self.assertEqual(len(machine.stages), 3)

    def test_accepts_workflow_dict(self):
        machine = StateMachine({"name": "wf", "stages": _stages()})
        self.assertEqual(len(machine.stages), 3)

    def test_empty_workflow_raises(self):
        with self.assertRaises(WorkflowError):
            StateMachine([])

    def test_stages_sorted_by_sequence(self):
        shuffled = list(reversed(_stages()))
        machine = StateMachine(shuffled)
        self.assertEqual([s["name"] for s in machine.stages], ["A", "B", "C"])


class NextStageTests(unittest.TestCase):
    def test_first_pending_with_met_deps_is_next(self):
        machine = StateMachine(_stages())
        self.assertEqual(machine.get_next_stage()["id"], "a")

    def test_in_progress_stage_takes_precedence(self):
        stages = _stages()
        stages[1]["status"] = "in_progress"
        machine = StateMachine(stages)
        self.assertEqual(machine.get_next_stage()["id"], "b")

    def test_next_after_completion(self):
        stages = _stages()
        stages[0]["status"] = "completed"
        machine = StateMachine(stages)
        self.assertEqual(machine.get_next_stage()["id"], "b")

    def test_none_when_all_done(self):
        stages = _stages()
        for stage in stages:
            stage["status"] = "completed"
        self.assertIsNone(StateMachine(stages).get_next_stage())


class TransitionTests(unittest.TestCase):
    def test_can_transition_only_when_deps_met(self):
        machine = StateMachine(_stages())
        self.assertTrue(machine.can_transition_to("a"))
        self.assertFalse(machine.can_transition_to("b"))

    def test_transition_marks_in_progress_and_sets_started(self):
        machine = StateMachine(_stages())
        stage = machine.transition_to("a")
        self.assertEqual(stage["status"], "in_progress")
        self.assertIsNotNone(stage["started_at"])

    def test_transition_by_name_is_case_insensitive(self):
        machine = StateMachine(_stages())
        stage = machine.transition_to("a")  # id
        self.assertEqual(stage["id"], "a")

    def test_transition_unknown_stage_raises(self):
        machine = StateMachine(_stages())
        with self.assertRaises(StateTransitionError) as ctx:
            machine.transition_to("zzz")
        self.assertEqual(ctx.exception.reason, "not_found")

    def test_transition_with_unmet_deps_raises(self):
        machine = StateMachine(_stages())
        with self.assertRaises(StateTransitionError) as ctx:
            machine.transition_to("b")
        self.assertEqual(ctx.exception.reason, "unmet_dependencies")

    def test_transition_already_finished_raises(self):
        stages = _stages()
        stages[0]["status"] = "completed"
        machine = StateMachine(stages)
        with self.assertRaises(StateTransitionError) as ctx:
            machine.transition_to("a")
        self.assertEqual(ctx.exception.reason, "already_finished")

    def test_complete_stage_sets_completed_at(self):
        machine = StateMachine(_stages())
        stage = machine.complete_stage("a")
        self.assertEqual(stage["status"], "completed")
        self.assertIsNotNone(stage["completed_at"])

    def test_complete_unknown_stage_raises(self):
        machine = StateMachine(_stages())
        with self.assertRaises(StateTransitionError):
            machine.complete_stage("nope")


class ProgressTests(unittest.TestCase):
    def test_zero_when_nothing_done(self):
        self.assertEqual(StateMachine(_stages()).get_progress(), 0.0)

    def test_partial_progress(self):
        stages = _stages()
        stages[0]["status"] = "completed"
        self.assertAlmostEqual(StateMachine(stages).get_progress(), 33.3, places=1)

    def test_full_progress_counts_skipped(self):
        stages = _stages()
        stages[0]["status"] = "completed"
        stages[1]["status"] = "skipped"
        stages[2]["status"] = "done"
        self.assertEqual(StateMachine(stages).get_progress(), 100.0)


class BlockerTests(unittest.TestCase):
    def test_pending_with_unmet_deps_is_blocker(self):
        machine = StateMachine(_stages())
        blockers = machine.get_blockers()
        names = {b["name"] for b in blockers}
        self.assertIn("B", names)
        self.assertIn("C", names)
        self.assertNotIn("A", names)  # A has no deps

    def test_explicitly_blocked_stage(self):
        stages = _stages()
        stages[0]["status"] = "blocked"
        blockers = StateMachine(stages).get_blockers()
        reasons = {b["stage_id"]: b["reason"] for b in blockers}
        self.assertEqual(reasons["a"], "explicitly_blocked")

    def test_unmet_dependencies_listed(self):
        machine = StateMachine(_stages())
        b_blocker = next(b for b in machine.get_blockers() if b["name"] == "B")
        self.assertEqual(b_blocker["unmet_dependencies"], ["a"])


class DelayTests(unittest.TestCase):
    def test_overdue_pending_stage_reported(self):
        past = datetime.now(timezone.utc) - timedelta(days=5)
        stages = _stages()
        stages[0]["deadline"] = past
        delays = StateMachine(stages).get_delays()
        self.assertEqual(len(delays), 1)
        self.assertGreaterEqual(delays[0]["delay_days"], 4)

    def test_future_deadline_not_reported(self):
        future = datetime.now(timezone.utc) + timedelta(days=5)
        stages = _stages()
        stages[0]["deadline"] = future
        self.assertEqual(StateMachine(stages).get_delays(), [])

    def test_completed_late_stage_reported(self):
        deadline = datetime(2024, 1, 1, tzinfo=timezone.utc)
        completed = datetime(2024, 1, 4, tzinfo=timezone.utc)
        stages = _stages()
        stages[0]["status"] = "completed"
        stages[0]["deadline"] = deadline
        stages[0]["completed_at"] = completed
        delays = StateMachine(stages).get_delays()
        self.assertEqual(delays[0]["delay_days"], 3)


class WorkloadTests(unittest.TestCase):
    def test_workload_grouped_by_team(self):
        stages = [
            {"id": "a", "name": "A", "status": "in_progress", "team_id": "t1", "sequence": 0},
            {"id": "b", "name": "B", "status": "completed", "team_id": "t1", "sequence": 1},
            {"id": "c", "name": "C", "status": "pending", "team_id": "t2", "sequence": 2},
        ]
        workload = StateMachine(stages).get_team_workload()
        self.assertEqual(workload["t1"]["total"], 2)
        self.assertEqual(workload["t1"]["active"], 1)
        self.assertEqual(workload["t1"]["done"], 1)
        self.assertEqual(workload["t2"]["pending"], 1)

    def test_unassigned_bucket(self):
        workload = StateMachine(_stages()).get_team_workload()
        self.assertIn("unassigned", workload)
        self.assertEqual(workload["unassigned"]["total"], 3)


class StatusReportTests(unittest.TestCase):
    def test_report_shape(self):
        report = StateMachine(_stages()).get_status_report()
        for key in ("total_stages", "progress_pct", "status_counts",
                    "current_stage", "next_stage", "blockers", "delays",
                    "team_workload", "is_complete", "stages"):
            self.assertIn(key, report)
        self.assertEqual(report["total_stages"], 3)
        self.assertEqual(report["next_stage"], "A")
        self.assertFalse(report["is_complete"])

    def test_report_is_complete(self):
        stages = _stages()
        for stage in stages:
            stage["status"] = "completed"
        report = StateMachine(stages).get_status_report()
        self.assertTrue(report["is_complete"])
        self.assertEqual(report["progress_pct"], 100.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
