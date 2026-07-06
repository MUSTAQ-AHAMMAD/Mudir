"""Pytest configuration and shared fixtures for the ORCHESTRA test suite.

The suite is designed to run with **no external services**: the AI models,
Ollama, WhatsApp API and (by default) the database are all replaced with the
in-memory fakes defined in :mod:`tests.fixtures.sample_data`.

Database integration tests (``tests/integration/test_database.py``) require a
real PostgreSQL instance and are skipped automatically unless
``ORCHESTRA_TEST_DATABASE_URL`` is set to a reachable async DSN, e.g.::

    postgresql+asyncpg://USER:PASSWORD@HOST:5432/orchestra_test
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Make the repository root importable (so ``orchestra`` and ``tests`` resolve)
# regardless of where pytest is invoked from.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures import sample_data  # noqa: E402


# ---------------------------------------------------------------------------
# Marker registration (mirrors pytest.ini for editors / standalone runs)
# ---------------------------------------------------------------------------
def pytest_configure(config: pytest.Config) -> None:
    for marker in (
        "unit: fast, isolated unit tests (no external services).",
        "integration: tests that exercise a real database or AI service.",
        "e2e: end-to-end workflow tests spanning multiple components.",
        "slow: tests that are comparatively slow to run.",
    ):
        config.addinivalue_line("markers", marker)


# ---------------------------------------------------------------------------
# Generic fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def event_loop():
    """Provide a fresh event loop for pytest-style async fixtures/tests."""

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def state() -> sample_data.InMemoryState:
    """A fresh in-memory state store."""

    return sample_data.InMemoryState()


@pytest.fixture
def fake_llm() -> sample_data.FakeLLM:
    """A deterministic fake LLM service."""

    return sample_data.FakeLLM()


@pytest.fixture
def orchestrator_bundle(state):
    """A fully-wired, in-memory orchestrator bundle (see build_orchestrator)."""

    return sample_data.build_orchestrator(state=state)


@pytest.fixture
def database_url() -> str | None:
    """Return the test database URL, or ``None`` when integration DB is disabled."""

    return os.environ.get("ORCHESTRA_TEST_DATABASE_URL")


@pytest.fixture
def require_database(database_url):
    """Skip a test unless a real PostgreSQL test database is configured."""

    if not database_url:
        pytest.skip("ORCHESTRA_TEST_DATABASE_URL not set; skipping DB integration test")
    return database_url
