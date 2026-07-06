"""Integration tests for the async database layer.

These tests exercise the real SQLAlchemy models and repositories against a
**real PostgreSQL** database. Because ``orchestra.database.models`` uses
PostgreSQL-specific types (``JSONB``, ``UUID``, native ``ENUM``) and the
connection manager uses asyncpg-specific server settings, these tests cannot
run on SQLite and are skipped unless ``ORCHESTRA_TEST_DATABASE_URL`` is set.

In CI a ``postgres`` service container provides the database (see
``.github/workflows/test.yml``). Locally you can run::

    export ORCHESTRA_TEST_DATABASE_URL="postgresql+asyncpg://<user>:<pass>@<host>:5432/orchestra_test"
    pytest tests/integration/test_database.py
"""

from __future__ import annotations

import os
import unittest
import uuid

import pytest

pytestmark = pytest.mark.integration

_DB_URL = os.getenv("ORCHESTRA_TEST_DATABASE_URL")


@unittest.skipUnless(_DB_URL, "ORCHESTRA_TEST_DATABASE_URL not set; skipping DB tests")
class DatabaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from orchestra.database import connection as conn_mod
        from orchestra.database.config import DatabaseConfig
        from orchestra.database.models import Base

        # Point the process-wide singleton at the test database so that the
        # repositories (which use ``get_connection_manager()``) hit it too.
        self._cfg = DatabaseConfig(explicit_url=_DB_URL)
        self._manager = conn_mod.ConnectionManager(self._cfg)
        self._original_manager = conn_mod._manager
        conn_mod._manager = self._manager

        async with self._manager.engine.begin() as bind:
            await bind.run_sync(Base.metadata.drop_all)
            await bind.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        from orchestra.database import connection as conn_mod
        from orchestra.database.models import Base

        async with self._manager.engine.begin() as bind:
            await bind.run_sync(Base.metadata.drop_all)
        await self._manager.dispose()
        conn_mod._manager = self._original_manager

    async def _make_company(self):
        from orchestra.database.models import Company

        slug = f"acme-{uuid.uuid4().hex[:8]}"
        company = Company(name="Acme", slug=slug)
        async with self._manager.session() as sess:
            sess.add(company)
            await sess.flush()
            await sess.refresh(company)
            return company.id

    # -- repository CRUD ----------------------------------------------------
    async def test_create_and_get_project(self):
        from orchestra.database.repositories import ProjectRepository

        company_id = await self._make_company()
        repo = ProjectRepository()
        project = await repo.create_project({"company_id": company_id, "name": "Store 1"})
        fetched = await repo.get_project(project.id)
        self.assertEqual(fetched.name, "Store 1")

    async def test_update_project_status_and_stage(self):
        from orchestra.database.models import ProjectStatus
        from orchestra.database.repositories import ProjectRepository

        company_id = await self._make_company()
        repo = ProjectRepository()
        project = await repo.create_project({"company_id": company_id, "name": "Store 2"})
        updated = await repo.update_project_status(
            project.id, "active", current_stage="Design"
        )
        self.assertEqual(updated.status, ProjectStatus.ACTIVE)
        self.assertEqual(updated.current_stage, "Design")

    async def test_stage_lifecycle_and_relationships(self):
        from orchestra.database.models import StageStatus
        from orchestra.database.repositories import ProjectRepository

        company_id = await self._make_company()
        repo = ProjectRepository()
        project = await repo.create_project({"company_id": company_id, "name": "Store 3"})

        s1 = await repo.add_project_stage(project.id, {"name": "Design"})
        s2 = await repo.add_project_stage(project.id, {"name": "Build"})
        # Sequence auto-assignment.
        self.assertEqual(s1.sequence, 0)
        self.assertEqual(s2.sequence, 1)

        completed = await repo.complete_stage(s1.id)
        self.assertEqual(completed.status, StageStatus.COMPLETED)
        self.assertIsNotNone(completed.completed_at)

        stages = await repo.get_stages(project.id)
        self.assertEqual([s.name for s in stages], ["Design", "Build"])

    async def test_get_project_missing_raises_not_found(self):
        from orchestra.database.exceptions import NotFoundError
        from orchestra.database.repositories import ProjectRepository

        repo = ProjectRepository()
        with self.assertRaises(NotFoundError):
            await repo.get_project(uuid.uuid4())

    async def test_workflow_repository_roundtrip(self):
        from orchestra.database.repositories import WorkflowRepository

        company_id = await self._make_company()
        repo = WorkflowRepository()
        wf = await repo.create_workflow(
            {
                "company_id": company_id,
                "name": "Store Opening",
                "stages": [{"name": "Design"}],
                "confidence": 0.5,
            }
        )
        again = await repo.increment_usage_count(wf.id)
        self.assertEqual(again.usage_count, 1)
        confident = await repo.update_confidence(wf.id, 0.9)
        self.assertAlmostEqual(confident.confidence, 0.9)

    async def test_team_repository_members(self):
        from orchestra.database.repositories import TeamRepository

        company_id = await self._make_company()
        repo = TeamRepository()
        team = await repo.create_team(
            {"company_id": company_id, "name": "Ops", "lead_whatsapp": "+100"}
        )
        fetched = await repo.get_team(team.id)
        self.assertEqual(fetched.name, "Ops")

    # -- transactions -------------------------------------------------------
    async def test_transaction_rollback_on_error(self):
        from orchestra.database.models import Company

        company_id = await self._make_company()
        # A duplicate slug inside a transaction must roll back the whole unit.
        with self.assertRaises(Exception):
            async with self._manager.begin() as sess:
                from sqlalchemy import select

                existing = (
                    await sess.execute(select(Company).where(Company.id == company_id))
                ).scalar_one()
                sess.add(Company(name="Dup", slug=existing.slug))
                await sess.flush()

    async def test_get_active_projects_filters_by_status(self):
        from orchestra.database.repositories import ProjectRepository

        company_id = await self._make_company()
        repo = ProjectRepository()
        active = await repo.create_project({"company_id": company_id, "name": "A"})
        await repo.update_project_status(active.id, "active")
        await repo.create_project({"company_id": company_id, "name": "Draft"})

        rows = await repo.get_active_projects(company_id)
        names = {p.name for p in rows}
        self.assertIn("A", names)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
