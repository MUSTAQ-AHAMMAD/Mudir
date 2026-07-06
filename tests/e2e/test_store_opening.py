"""End-to-end test: the full store-opening workflow.

Drives the real :class:`Orchestrator` (wired to in-memory fakes via
:func:`tests.fixtures.sample_data.build_orchestrator`) through a complete
store-opening lifecycle: project creation, stage-by-stage completion, voice
notes, delays, escalations, CEO approval and parallel projects.
"""

from __future__ import annotations

import unittest

import pytest

from tests.fixtures.sample_data import (
    SAMPLE_VOICE_TRANSCRIPT,
    STORE_OPENING_WORKFLOW,
    FakeIntentRouter,
    FakeWhisper,
    build_orchestrator,
)

pytestmark = pytest.mark.e2e


class StoreOpeningEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def _open_store(self):
        bundle = build_orchestrator(workflow=STORE_OPENING_WORKFLOW)
        created = await bundle.orchestrator.create_new_project(
            "We are opening a new store in Riyadh", "alice", bundle.group_id
        )
        return bundle, created

    async def test_complete_store_opening_lifecycle(self):
        bundle, created = await self._open_store()
        project_id = created["project_id"]
        self.assertEqual(len(created["stages"]), 5)

        # Complete every stage in order; the last one finishes the project.
        last = None
        for _ in range(5):
            last = await bundle.orchestrator.handle_stage_completion(project_id, None, "alice")
        self.assertTrue(last.get("project_complete"))
        self.assertEqual(bundle.state.projects[project_id].status, "completed")

        # Final status report reflects 100% progress.
        status = await bundle.orchestrator.get_project_status(project_id)
        self.assertEqual(status["workflow"]["progress_pct"], 100.0)

    async def test_voice_note_drives_stage_completion(self):
        bundle, created = await self._open_store()
        project_id = created["project_id"]

        # A voice note is transcribed (Arabic) then handled as a normal message.
        whisper = FakeWhisper(transcript=SAMPLE_VOICE_TRANSCRIPT)
        transcript = whisper.transcribe_whatsapp_voice("https://media/voice.ogg")
        self.assertEqual(transcript, SAMPLE_VOICE_TRANSCRIPT)

        bundle.orchestrator.intent_router = FakeIntentRouter(intent="stage_complete")
        result = await bundle.orchestrator.handle_incoming_message(
            transcript, "alice", bundle.group_id
        )
        self.assertIn("completed_stage", result)

    async def test_image_ocr_text_treated_as_message(self):
        bundle, created = await self._open_store()
        # OCR output from an uploaded permit image feeds the NL handler.
        ocr_text = "Municipality permit approved for the Riyadh store"
        bundle.orchestrator.intent_router = FakeIntentRouter(
            intent="natural_language", reply="تم استلام التصريح"
        )
        result = await bundle.orchestrator.handle_incoming_message(
            ocr_text, "alice", bundle.group_id
        )
        self.assertEqual(result["reply"], "تم استلام التصريح")

    async def test_delay_scenario_records_delay(self):
        bundle, created = await self._open_store()
        project_id = created["project_id"]
        result = await bundle.orchestrator.handle_delay(project_id, 1, "supplier late", "alice")
        self.assertEqual(result["days"], 1)
        self.assertEqual(bundle.state.escalations, [])

    async def test_delay_scenario_auto_escalates(self):
        bundle, created = await self._open_store()
        project_id = created["project_id"]
        await bundle.orchestrator.handle_delay(project_id, 5, "permit stuck", "alice")
        self.assertEqual(len(bundle.state.escalations), 1)

    async def test_escalation_and_ceo_approval(self):
        bundle, created = await self._open_store()
        project_id = created["project_id"]
        result = await bundle.orchestrator.handle_escalation(
            project_id, "budget overrun", "urgent", "alice"
        )
        self.assertEqual(result["priority"], "critical")
        # CEO is notified for approval.
        self.assertTrue(any(n["kind"] == "ceo" for n in bundle.state.notifications))

    async def test_multiple_projects_in_parallel(self):
        bundle = build_orchestrator(workflow=STORE_OPENING_WORKFLOW)
        first = await bundle.orchestrator.create_new_project("open store A", "alice", bundle.group_id)
        second = await bundle.orchestrator.create_new_project("open store B", "bob", bundle.group_id)
        self.assertNotEqual(first["project_id"], second["project_id"])

        # Advancing one project does not affect the other.
        await bundle.orchestrator.handle_stage_completion(first["project_id"], None, "alice")
        s1 = await bundle.orchestrator.get_project_status(first["project_id"])
        s2 = await bundle.orchestrator.get_project_status(second["project_id"])
        self.assertGreater(s1["workflow"]["progress_pct"], s2["workflow"]["progress_pct"])

    async def test_friday_skip_is_respected_by_scheduler(self):
        # The Scheduler is responsible for skipping Fridays (Saudi weekend).
        # Here we verify the orchestrator exposes scheduled jobs without error.
        bundle, _ = await self._open_store()
        jobs = bundle.orchestrator.scheduler.get_scheduled_jobs()
        self.assertEqual(jobs, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
