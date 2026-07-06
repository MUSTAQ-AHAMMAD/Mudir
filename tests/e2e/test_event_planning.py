"""End-to-end test: an event-planning workflow.

The event-planning workflow contains **parallel dependencies** (the Execution
stage depends on both Catering and Promotion), exercising the state machine's
dependency handling in a real project lifecycle for yet another industry.
"""

from __future__ import annotations

import unittest

import pytest

from tests.fixtures.sample_data import (
    EVENT_PLANNING_WORKFLOW,
    STORE_OPENING_WORKFLOW,
    build_orchestrator,
)

pytestmark = pytest.mark.e2e


class EventPlanningEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def _plan_event(self):
        bundle = build_orchestrator(workflow=EVENT_PLANNING_WORKFLOW)
        created = await bundle.orchestrator.create_new_project(
            "We are planning a product launch event", "coordinator", bundle.group_id
        )
        return bundle, created

    async def test_event_workflow_materialises_stages(self):
        bundle, created = await self._plan_event()
        expected = len(EVENT_PLANNING_WORKFLOW["stages"])
        self.assertEqual(len(created["stages"]), expected)

    async def test_event_workflow_completes_all_stages(self):
        bundle, created = await self._plan_event()
        project_id = created["project_id"]
        stage_count = len(created["stages"])
        last = None
        for _ in range(stage_count):
            last = await bundle.orchestrator.handle_stage_completion(project_id, None, "coordinator")
        self.assertTrue(last.get("project_complete"))
        status = await bundle.orchestrator.get_project_status(project_id)
        self.assertEqual(status["workflow"]["progress_pct"], 100.0)

    async def test_different_industry_workflow_is_independent(self):
        bundle = build_orchestrator(workflow=EVENT_PLANNING_WORKFLOW)
        event = await bundle.orchestrator.create_new_project(
            "plan a conference", "coordinator", bundle.group_id
        )
        bundle.orchestrator.workflow_engine._llm._workflow = STORE_OPENING_WORKFLOW
        store = await bundle.orchestrator.create_new_project(
            "open a new store", "ops", bundle.group_id
        )
        self.assertNotEqual(event["workflow_id"], store["workflow_id"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
