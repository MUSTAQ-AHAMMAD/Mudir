"""Unit tests for :class:`orchestra.engine.workflow_engine.WorkflowEngine`.

The learning/suggestion paths call the LLM, so a :class:`FakeLLM` is injected.
Validation, merging and confidence scoring are pure and tested directly.
"""

from __future__ import annotations

import unittest

from tests.fixtures.sample_data import (
    STORE_OPENING_WORKFLOW,
    FakeLLM,
)

from orchestra.engine.exceptions import WorkflowError
from orchestra.engine.workflow_engine import WorkflowEngine


class LearnWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_learn_workflow_returns_named_workflow_with_confidence(self):
        engine = WorkflowEngine(llm_service=FakeLLM(workflow=STORE_OPENING_WORKFLOW))
        wf = await engine.learn_workflow("open a store", industry="retail")
        self.assertEqual(wf["industry"], "retail")
        self.assertEqual(len(wf["stages"]), 5)
        self.assertGreater(wf["confidence"], 0.5)
        # Stages are normalised into the canonical template shape.
        self.assertEqual(
            set(wf["stages"][0].keys()), {"name", "description", "owner", "depends_on"}
        )

    async def test_learn_workflow_names_from_industry_when_llm_omits_name(self):
        llm = FakeLLM(workflow={"workflow_name": None, "stages": [{"name": "X"}]})
        engine = WorkflowEngine(llm_service=llm)
        wf = await engine.learn_workflow("do things", industry="logistics")
        self.assertEqual(wf["workflow_name"], "logistics workflow")

    async def test_learn_workflow_no_stages_raises(self):
        engine = WorkflowEngine(llm_service=FakeLLM(workflow={"workflow_name": "e", "stages": []}))
        with self.assertRaises(WorkflowError):
            await engine.learn_workflow("nothing useful")


class ExtractStagesTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_stages_cleans_dependencies(self):
        llm = FakeLLM(workflow={"stages": [
            {"title": "Alpha", "dependencies": "seed"},  # title + scalar dep
            {"name": "Beta", "depends_on": ["Alpha"]},
            {"not_a_stage": True},  # dropped (no name)
        ]})
        engine = WorkflowEngine(llm_service=llm)
        stages = await engine.extract_stages("...")
        self.assertEqual([s["name"] for s in stages], ["Alpha", "Beta"])
        self.assertEqual(stages[0]["depends_on"], ["seed"])


class ValidateWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = WorkflowEngine(llm_service=FakeLLM())

    def test_valid_linear_workflow(self):
        result = self.engine.validate_workflow(STORE_OPENING_WORKFLOW)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_empty_workflow_invalid(self):
        result = self.engine.validate_workflow({"stages": []})
        self.assertFalse(result["valid"])

    def test_missing_dependency_is_error(self):
        wf = {"stages": [{"name": "A", "depends_on": ["ghost"]}]}
        result = self.engine.validate_workflow(wf)
        self.assertFalse(result["valid"])
        self.assertTrue(any("unknown stage" in e for e in result["errors"]))

    def test_cycle_detected(self):
        wf = {"stages": [
            {"name": "A", "depends_on": ["B"]},
            {"name": "B", "depends_on": ["A"]},
        ]}
        result = self.engine.validate_workflow(wf)
        self.assertFalse(result["valid"])
        self.assertTrue(any("cycle" in e for e in result["errors"]))

    def test_duplicate_name_is_warning_not_error(self):
        wf = {"stages": [{"name": "A"}, {"name": "a"}]}
        result = self.engine.validate_workflow(wf)
        self.assertTrue(result["valid"])
        self.assertTrue(result["warnings"])


class MergeWorkflowsTests(unittest.TestCase):
    def setUp(self):
        self.engine = WorkflowEngine(llm_service=FakeLLM())

    def test_union_of_dependencies_for_matching_stage(self):
        wf1 = {"stages": [{"name": "Build", "depends_on": ["Plan"]}]}
        wf2 = {"stages": [{"name": "build", "depends_on": ["Budget"]}]}
        merged = self.engine.merge_workflows(wf1, wf2)
        self.assertEqual(len(merged["stages"]), 1)
        self.assertEqual(set(merged["stages"][0]["depends_on"]), {"Plan", "Budget"})

    def test_appends_new_stages_from_second(self):
        wf1 = {"stages": [{"name": "A"}]}
        wf2 = {"stages": [{"name": "B"}]}
        merged = self.engine.merge_workflows(wf1, wf2)
        self.assertEqual([s["name"] for s in merged["stages"]], ["A", "B"])

    def test_adopts_description_from_second_when_missing(self):
        wf1 = {"stages": [{"name": "A", "description": None}]}
        wf2 = {"stages": [{"name": "A", "description": "detail"}]}
        merged = self.engine.merge_workflows(wf1, wf2)
        self.assertEqual(merged["stages"][0]["description"], "detail")


class CalculateConfidenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = WorkflowEngine(llm_service=FakeLLM())

    def test_empty_workflow_zero(self):
        self.assertEqual(self.engine.calculate_confidence({"stages": []}), 0.0)

    def test_well_formed_workflow_scores_high(self):
        score = self.engine.calculate_confidence(STORE_OPENING_WORKFLOW)
        self.assertGreaterEqual(score, 0.8)
        self.assertLessEqual(score, 1.0)

    def test_invalid_workflow_scores_low(self):
        wf = {"stages": [{"name": "A", "depends_on": ["ghost"]}]}
        score = self.engine.calculate_confidence(wf)
        self.assertLessEqual(score, 0.3)
        self.assertGreaterEqual(score, 0.1)

    def test_usage_count_boosts_score(self):
        class WF:
            stages = STORE_OPENING_WORKFLOW["stages"]
            usage_count = 5

        boosted = self.engine.calculate_confidence(WF())
        base = self.engine.calculate_confidence({"stages": STORE_OPENING_WORKFLOW["stages"]})
        self.assertGreaterEqual(boosted, base)


class AutoSuggestTests(unittest.IsolatedAsyncioTestCase):
    async def test_suggestions_returned_from_llm(self):
        from tests.fixtures.sample_data import InMemoryState, FakeWorkflowRepo, new_id
        from types import SimpleNamespace

        state = InMemoryState()
        wf_id = new_id()
        state.workflows[wf_id] = SimpleNamespace(
            id=wf_id, stages=STORE_OPENING_WORKFLOW["stages"], usage_count=1
        )
        llm = FakeLLM()
        llm.suggestions = [{"type": "parallelize", "stage": "IT setup", "detail": "run alongside stocking", "impact": "medium"}]
        engine = WorkflowEngine(llm_service=llm, workflow_repo=FakeWorkflowRepo(state))
        suggestions = await engine.auto_suggest_optimizations(wf_id, project_history=["late by 3 days"])
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["type"], "parallelize")

    async def test_malformed_llm_response_returns_empty(self):
        from tests.fixtures.sample_data import InMemoryState, FakeWorkflowRepo, new_id
        from types import SimpleNamespace

        state = InMemoryState()
        wf_id = new_id()
        state.workflows[wf_id] = SimpleNamespace(id=wf_id, stages=[], usage_count=0)
        llm = FakeLLM()
        llm.suggestions = []  # _chat_json returns {"suggestions": []}
        engine = WorkflowEngine(llm_service=llm, workflow_repo=FakeWorkflowRepo(state))
        self.assertEqual(await engine.auto_suggest_optimizations(wf_id), [])


class ImproveWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_improve_merges_and_persists(self):
        from tests.fixtures.sample_data import InMemoryState, FakeWorkflowRepo, new_id
        from types import SimpleNamespace

        state = InMemoryState()
        wf_id = new_id()
        state.workflows[wf_id] = SimpleNamespace(
            id=wf_id, stages=[{"name": "A", "depends_on": []}], usage_count=0,
        )
        engine = WorkflowEngine(llm_service=FakeLLM(), workflow_repo=FakeWorkflowRepo(state))
        updated = await engine.improve_workflow(wf_id, {"stages": [{"name": "B", "depends_on": ["A"]}]})
        names = [s["name"] for s in updated.stages]
        self.assertEqual(names, ["A", "B"])
        self.assertEqual(state.workflows[wf_id].usage_count, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
