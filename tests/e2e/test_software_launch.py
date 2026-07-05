"""End-to-end test: a software-launch workflow.

Demonstrates that the same orchestration engine drives a completely different
industry workflow (software development) with no code changes — the workflow
is learned dynamically and materialised into project stages.
"""

from __future__ import annotations

import unittest

import pytest

from tests.fixtures.sample_data import (
    SOFTWARE_LAUNCH_WORKFLOW,
    STORE_OPENING_WORKFLOW,
    build_orchestrator,
)

pytestmark = pytest.mark.e2e


class SoftwareLaunchEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def _launch(self):
        bundle = build_orchestrator(workflow=SOFTWARE_LAUNCH_WORKFLOW)
        created = await bundle.orchestrator.create_new_project(
            "We are launching a new mobile app", "dev-lead", bundle.group_id
        )
        return bundle, created

    async def test_software_workflow_materialises_all_stages(self):
        bundle, created = await self._launch()
        self.assertEqual(len(created["stages"]), 5)
        project_id = created["project_id"]
        self.assertEqual(len(bundle.state.stages[project_id]), 5)

    async def test_software_workflow_completes(self):
        bundle, created = await self._launch()
        project_id = created["project_id"]
        last = None
        for _ in range(5):
            last = await bundle.orchestrator.handle_stage_completion(project_id, None, "dev-lead")
        self.assertTrue(last.get("project_complete"))
        status = await bundle.orchestrator.get_project_status(project_id)
        self.assertEqual(status["workflow"]["progress_pct"], 100.0)

    async def test_different_industry_workflow_is_independent(self):
        # A software project and a retail project can coexist with distinct
        # workflows in the same company.
        bundle = build_orchestrator(workflow=SOFTWARE_LAUNCH_WORKFLOW)
        software = await bundle.orchestrator.create_new_project(
            "launch our SaaS platform", "dev-lead", bundle.group_id
        )
        # Re-learn with a retail workflow for a second project.
        bundle.orchestrator.workflow_engine._llm._workflow = STORE_OPENING_WORKFLOW
        retail = await bundle.orchestrator.create_new_project(
            "open a flagship store", "ops", bundle.group_id
        )
        self.assertNotEqual(software["workflow_id"], retail["workflow_id"])
        self.assertEqual(len(bundle.state.stages[retail["project_id"]]), 5)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
