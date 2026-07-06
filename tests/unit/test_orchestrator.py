"""Unit tests for :class:`orchestra.engine.orchestrator.Orchestrator`.

The orchestrator is wired with in-memory fakes (see
:func:`tests.fixtures.sample_data.build_orchestrator`) so its coordination
logic can be tested without a database, LLM or WhatsApp API.
"""

from __future__ import annotations

import unittest

from tests.fixtures.sample_data import (
    STORE_OPENING_WORKFLOW,
    FakeIntentRouter,
    build_orchestrator,
)

from orchestra.engine.exceptions import ProjectNotFoundError


class HandleIncomingMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_project_intent_routes_to_creation(self):
        bundle = build_orchestrator(
            intent_router=FakeIntentRouter(intent="create_project"),
        )
        result = await bundle.orchestrator.handle_incoming_message(
            "We are opening a store", "alice", bundle.group_id
        )
        self.assertIn("Created project", result["reply"])
        self.assertIn("project_id", result)

    async def test_status_intent_without_project_falls_back(self):
        # No active project resolved -> status handler is skipped, NL fallback used.
        bundle = build_orchestrator(intent_router=FakeIntentRouter(intent="status", reply="hi"))
        result = await bundle.orchestrator.handle_incoming_message("status?", "bob", bundle.group_id)
        self.assertEqual(result["reply"], "hi")

    async def test_natural_language_fallback(self):
        bundle = build_orchestrator(
            intent_router=FakeIntentRouter(intent="natural_language", reply="Marhaba!"),
        )
        result = await bundle.orchestrator.handle_incoming_message("hello", "carol", bundle.group_id)
        self.assertEqual(result["reply"], "Marhaba!")

    async def test_inbound_message_is_logged(self):
        bundle = build_orchestrator(intent_router=FakeIntentRouter())
        await bundle.orchestrator.handle_incoming_message("hi", "dave", bundle.group_id)
        self.assertTrue(bundle.state.messages)
        self.assertEqual(bundle.state.messages[0]["direction"], "inbound")


class CreateProjectTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_new_project_materialises_stages(self):
        bundle = build_orchestrator(workflow=STORE_OPENING_WORKFLOW)
        result = await bundle.orchestrator.create_new_project(
            "open a store", "alice", bundle.group_id
        )
        self.assertEqual(len(result["stages"]), 5)
        # Stages persisted to the store.
        project_id = result["project_id"]
        self.assertEqual(len(bundle.state.stages[project_id]), 5)
        # A welcome message was sent to the group.
        self.assertTrue(any(n["kind"] == "welcome" for n in bundle.state.notifications))

    async def test_create_without_company_raises(self):
        bundle = build_orchestrator()
        with self.assertRaises(ProjectNotFoundError):
            # No group_id and no company_id -> cannot resolve company.
            await bundle.orchestrator.create_new_project("open a store", "alice", None)

    async def test_workflow_reused_when_same_name(self):
        bundle = build_orchestrator(workflow=STORE_OPENING_WORKFLOW)
        first = await bundle.orchestrator.create_new_project("open store", "a", bundle.group_id)
        second = await bundle.orchestrator.create_new_project("open store", "a", bundle.group_id)
        # Same learned workflow name -> the workflow record is reused.
        self.assertEqual(first["workflow_id"], second["workflow_id"])


class StageCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def _project(self):
        bundle = build_orchestrator(workflow=STORE_OPENING_WORKFLOW)
        created = await bundle.orchestrator.create_new_project("open a store", "alice", bundle.group_id)
        return bundle, created["project_id"]

    async def test_complete_first_stage_advances_to_next(self):
        bundle, project_id = await self._project()
        result = await bundle.orchestrator.handle_stage_completion(project_id, None, "alice")
        self.assertEqual(result["completed_stage"], "Site selection")
        self.assertEqual(result["next_stage"], "Construction")

    async def test_completing_all_stages_finishes_project(self):
        bundle, project_id = await self._project()
        # Complete all five stages in sequence (stage_id=None auto-selects next).
        last = None
        for _ in range(5):
            last = await bundle.orchestrator.handle_stage_completion(project_id, None, "alice")
        self.assertTrue(last.get("project_complete"))
        self.assertEqual(bundle.state.projects[project_id].status, "completed")

    async def test_no_stages_raises(self):
        from orchestra.engine.exceptions import WorkflowError

        bundle = build_orchestrator()
        # Create an empty project directly in the store.
        project = await bundle.project_repo.create_project({"company_id": bundle.company_id, "name": "Empty"})
        with self.assertRaises(WorkflowError):
            await bundle.orchestrator.handle_stage_completion(project.id, None, "x")


class DelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_small_delay_recorded_without_escalation(self):
        bundle = build_orchestrator()
        project = await bundle.project_repo.create_project({"company_id": bundle.company_id, "name": "P"})
        result = await bundle.orchestrator.handle_delay(project.id, 1, "supplier late", "alice")
        self.assertEqual(result["days"], 1)
        self.assertEqual(bundle.state.projects[str(project.id)].metadata_["delays"][0]["reason"], "supplier late")
        self.assertEqual(bundle.state.escalations, [])

    async def test_large_delay_triggers_escalation(self):
        bundle = build_orchestrator()
        project = await bundle.project_repo.create_project({"company_id": bundle.company_id, "name": "P"})
        await bundle.orchestrator.handle_delay(project.id, 5, "major issue", "alice")
        self.assertEqual(len(bundle.state.escalations), 1)
        self.assertEqual(bundle.state.escalations[0].priority, "medium")


class EscalationTests(unittest.IsolatedAsyncioTestCase):
    async def test_escalation_notifies_ceo(self):
        bundle = build_orchestrator()
        project = await bundle.project_repo.create_project({"company_id": bundle.company_id, "name": "P"})
        result = await bundle.orchestrator.handle_escalation(project.id, "roof leak", "urgent", "alice")
        self.assertEqual(result["priority"], "critical")  # urgent -> critical
        self.assertTrue(any(n["kind"] == "ceo" for n in bundle.state.notifications))

    async def test_unknown_severity_defaults_to_high(self):
        bundle = build_orchestrator()
        project = await bundle.project_repo.create_project({"company_id": bundle.company_id, "name": "P"})
        result = await bundle.orchestrator.handle_escalation(project.id, "issue", "weird", "alice")
        self.assertEqual(result["priority"], "high")


class ProjectStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_includes_workflow_and_reply(self):
        bundle = build_orchestrator(workflow=STORE_OPENING_WORKFLOW)
        created = await bundle.orchestrator.create_new_project("open a store", "alice", bundle.group_id)
        status = await bundle.orchestrator.get_project_status(created["project_id"])
        self.assertIn("workflow", status)
        self.assertIn("progress_pct", status["workflow"])
        self.assertIn("📋", status["reply"])


class NaturalLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_natural_language_uses_router_fallback(self):
        bundle = build_orchestrator(intent_router=FakeIntentRouter(reply="How can I help?"))
        result = await bundle.orchestrator.handle_natural_language("hi", None, "alice")
        self.assertEqual(result["reply"], "How can I help?")


class HelperTests(unittest.TestCase):
    def test_coerce_int(self):
        from orchestra.engine.orchestrator import Orchestrator

        self.assertEqual(Orchestrator._coerce_int("3"), 3)
        self.assertEqual(Orchestrator._coerce_int(None, default=7), 7)

    def test_normalise_priority(self):
        from orchestra.engine.orchestrator import Orchestrator

        self.assertEqual(Orchestrator._normalise_priority("URGENT"), "critical")
        self.assertEqual(Orchestrator._normalise_priority("med"), "medium")
        self.assertEqual(Orchestrator._normalise_priority("???"), "high")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
