# Developer Guide — Mudir / ORCHESTRA

This guide is for contributors extending Mudir. Read
[.github/CONTRIBUTING.md](.github/CONTRIBUTING.md) for the PR process and
[docs/architecture.mermaid](docs/architecture.mermaid) for diagrams.

---

## 1. Project architecture

Mudir is a **dual-stack** system:

- **Backend** (`backend/`, Node.js/Express) — the WhatsApp webhook, command
  parser, REST API for the dashboard, and cron jobs.
- **ORCHESTRA engine** (`orchestra/`, Python) — the AI coordination brain:
  self-hosted AI services, the async database layer, the orchestration engine
  and the WhatsApp integration layer.
- **Frontend** (`frontend/`, React + Vite + Tailwind) — the admin dashboard.

The engine is designed for **dependency injection** and **lazy imports**: heavy
ML/DB libraries are only imported when actually used, so the code can be
imported and unit-tested without them.

---

## 2. Code structure

```
orchestra/
├── services/            Self-hosted AI services
│   ├── llm_service.py         Ollama chat + intent/workflow extraction
│   ├── whisper_service.py     whisper.cpp speech-to-text
│   ├── embeddings_service.py  BGE-M3 embeddings + cosine similarity
│   ├── vector_db_service.py   ChromaDB wrapper
│   ├── sentiment_service.py   Arabic/English sentiment
│   ├── translation_service.py NLLB translation + language detection
│   └── config.py              Shared config + logging
├── database/            Async data layer (SQLAlchemy 2.0)
│   ├── models.py              PostgreSQL models (JSONB, UUID, native enums)
│   ├── repositories/          One repository per aggregate
│   ├── connection.py          Engine + session/transaction scopes
│   ├── schema.sql             Canonical schema
│   └── migrations/            Alembic migrations
├── engine/              Orchestration
│   ├── orchestrator.py        Orchestrator + get_orchestrator() singleton
│   ├── workflow_engine.py     Learn / validate / merge / score workflows
│   ├── state_machine.py       Stage transitions, progress, blockers
│   ├── project_manager.py     Project lifecycle
│   ├── task_manager.py        Task lifecycle
│   ├── team_coordinator.py    Dispatch to teams (WhatsAppSender protocol)
│   ├── intent_router.py       Classify intent + route to handler
│   ├── context_manager.py     Conversation context
│   └── scheduler.py           Reminders, Friday-skip scheduling
└── whatsapp/            WhatsApp integration
    ├── client.py              WATIClient (async, injectable transport)
    ├── sender.py              WhatsAppSender (implements engine protocol)
    ├── webhook.py             WebhookReceiver (signature verify, routing)
    ├── handlers.py            Per-message-type handlers
    ├── session_manager.py     Group ↔ company session mapping
    ├── templates.py           Bilingual (AR/EN) copy
    └── middleware.py          Cross-cutting request handling
```

Key conventions (verify against the code before relying on them):

- Services expose a **class**, module-level functions, and a `get_service()`
  singleton.
- Engine components are **async** and pull services/repos via lazy `@property`
  accessors so they can be injected in tests.
- The engine sends WhatsApp messages through an injected **`WhatsAppSender`
  protocol** (`send_message` / `send_group_message`); with no transport it
  degrades gracefully (logs + communication logs).
- Database enums use the `_pg_enum()` helper (`values_callable`) so persisted
  values match the lowercase values in `schema.sql`.

---

## 3. Adding a new workflow

Workflows are **data**, not code. You usually don't write a workflow by hand:

1. The `WorkflowEngine.learn_workflow()` infers stages from a conversation via
   the LLM (`extract_workflow`).
2. `validate_workflow()` checks for cycles and dangling dependencies.
3. `calculate_confidence()` scores it; `merge_workflows()` reconciles duplicates.
4. Persist via the `WorkflowRepository`; it's reused for future projects of the
   same name.

To add a **built-in** workflow for a new industry, define its stages
(`name`, `description`, `owner`, `depends_on`) and seed it through the workflow
repository. The state machine adapts to any number of stages and parallel
dependencies automatically.

---

## 4. Extending AI models

- **Swap the LLM:** point `llm_service` at a different Ollama model via config
  (`OLLAMA_MODELS` / the service's `model` param). No code change needed.
- **Swap embeddings/translation/sentiment:** each service loads its model lazily
  in a `.model`/`.pipeline` property or `_ensure_loaded()`. Change the model path
  in config; keep the public method signatures stable.
- **Add a new capability:** create `orchestra/services/<name>_service.py`
  following the existing pattern (class + module functions + `get_service()`),
  lazy-import heavy deps, and add it to `orchestra/services/__init__.py`.

---

## 5. Custom integrations

- **Different messaging provider:** implement the engine's `WhatsAppSender`
  protocol (`send_message` / `send_group_message`) and inject it into the
  `Orchestrator` / `TeamCoordinator`. Implement a `WebhookReceiver`-equivalent to
  translate inbound payloads.
- **Embedding the engine:** call
  `orchestra.engine.orchestrator.get_orchestrator()` and
  `await handle_incoming_message(text, sender, group_id)`.

---

## 6. Testing guide

The Python suite lives in `tests/` and mocks every external service, so it runs
anywhere (no GPU, models, or network).

```
tests/
├── conftest.py              sys.path, markers, shared fixtures
├── fixtures/sample_data.py  sample companies/teams/workflows + all fakes +
│                            build_orchestrator() in-memory wiring
├── unit/                    state machine, workflow engine, orchestrator,
│                            whatsapp client, webhook
├── integration/             ai services (mocked), database (real PostgreSQL)
└── e2e/                     store opening, software launch, event planning
```

Run:
```bash
pip install -r requirements-test.txt
pytest                                   # everything
pytest -m unit                           # only unit tests
pytest -m e2e                            # only end-to-end tests
pytest --cov=orchestra --cov-report=term-missing
```

Conventions:
- Async tests use `unittest.IsolatedAsyncioTestCase` (no pytest-asyncio needed).
- Markers: `unit`, `integration`, `e2e`, `slow` (declared in `pytest.ini`).
- Database tests are **skipped** unless `ORCHESTRA_TEST_DATABASE_URL` points at a
  real PostgreSQL (models use PostgreSQL-only types).
- Reuse the fakes and `build_orchestrator()` in `tests/fixtures/sample_data.py`
  rather than re-mocking.

The existing WhatsApp package tests (`orchestra/whatsapp/tests/test_whatsapp.py`)
use stdlib `unittest` and run with `python -m unittest orchestra.whatsapp.tests.test_whatsapp`.

Node backend: `cd backend && npm test` (Jest). Frontend: `cd frontend && npm test`
(Vitest).

---

## 7. Contributing guidelines

See [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md). In short: fork/branch,
keep changes focused, add tests, ensure `pytest` (and the JS suites you touch)
pass, and open a PR against `main` using the templates.

---

## 8. Coding standards

- **Python:** PEP 8, full type hints, module/class/function docstrings, lazy
  imports for heavy deps, dependency injection over globals. Keep functions small
  and pure where possible.
- **JavaScript/React:** follow the existing ESLint/Prettier config; colocate
  component tests as `*.test.js(x)`; keep the dashboard Arabic-first (RTL) and
  dark-mode aware.
- **Commits:** imperative, scoped messages (e.g. "engine: fix stage advance").
- **Security:** never commit secrets; validate/parameterise all external input;
  keep webhook signature verification intact. See [docs/security.md](docs/security.md).
