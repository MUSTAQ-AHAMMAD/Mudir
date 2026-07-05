# Changelog

All notable changes to Mudir / ORCHESTRA are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-07-05

First production release: an AI project coordinator that runs inside WhatsApp
for multi-team retail store openings, with a self-hosted AI stack and a full
production deployment configuration.

### Added

- **WhatsApp coordinator (backend)** — Node.js/Express webhook, command parser
  (`/new_project`, `/assign`, `/complete`, `/extend`, `/status`, `/escalate`),
  bilingual (Arabic-first) replies, sequential team state machine, daily summary
  + overdue-escalation cron (Saudi working week aware), and a REST API.
- **Voice notes** — transcription and intent mapping with confirmation before
  executing commands.
- **Self-hosted AI stack (ORCHESTRA)** — Ollama (Llama 3 / Phi-3), Whisper
  transcription, BGE-M3 embeddings, ChromaDB vector DB, NLLB translation and
  Arabic sentiment, plus a hardware auto-detection installer (`auto-install.sh`).
- **Admin dashboard (frontend)** — React 18 + Vite + Tailwind, Arabic-first RTL,
  dark mode, Chart.js analytics, Supabase auth/real-time with REST fallback.
- **Database layer** — SQLAlchemy 2.0 async models, repositories, canonical
  `schema.sql`, and Alembic migrations.
- **Production deployment configuration:**
  - Multi-stage Alpine Dockerfiles for backend, frontend and Ollama.
  - Docker Compose base stack (ollama, whisper, chromadb, postgres, backend,
    frontend, nginx) with health checks, named volumes, isolated networks,
    restart policies and resource limits.
  - GPU and CPU compose overlays, plus an optional Prometheus + Grafana
    monitoring overlay.
  - Operational scripts: `deploy.sh`, `backup.sh`, `update.sh`, `monitor.sh`,
    `ssl-renew.sh`.
  - Edge nginx reverse proxy: TLS termination, HTTP→HTTPS redirect, rate
    limiting, WebSocket support, security headers and load balancing.
  - Let's Encrypt setup + auto-renewal documentation.
  - Prometheus scrape config, alert rules and Grafana dashboards (system,
    model performance, project/WhatsApp metrics).
  - Optional Kubernetes manifests (`k8s/deployment.yaml`).
  - GitHub Actions CI/CD (test → build & push images → SSH deploy).
  - `.env.production` / `.env.staging` templates and a deployment guide
    (`DEPLOYMENT.md`).
- **Automated testing (Python engine):**
  - `pytest` suite covering unit (state machine, workflow engine, orchestrator,
    WhatsApp client, webhook), integration (AI services mocked; database against
    real PostgreSQL) and end-to-end workflows (store opening, software launch,
    event planning).
  - Reusable fixtures and in-memory fakes (`tests/fixtures/sample_data.py`) that
    mock every external service, so the suite runs with no GPU, models or network.
  - `pytest.ini`, `requirements-test.txt`, and a CI workflow
    (`.github/workflows/test.yml`) running the suite on Python 3.10/3.11/3.12
    with a PostgreSQL service container and coverage reporting.
- **Documentation:** comprehensive English guides (`README`, `USER_GUIDE`,
  `ADMIN_GUIDE`, `API_REFERENCE`, `DEVELOPER_GUIDE`), operations/security/
  performance docs (`docs/security.md`, `docs/performance.md`), Mermaid
  architecture & sequence diagrams (`docs/architecture.mermaid`), Arabic
  translations (`docs/ar/`), contribution guidelines and issue templates
  (`.github/`), and an MIT `LICENSE`.

### Fixed

- `ProjectManager.update_project_status` now forwards the optional
  `current_stage` argument, fixing a latent `TypeError` when the orchestrator
  advanced a project's stage on completion.

### Security

- Secrets kept in environment variables (never committed).
- HTTPS-only with HSTS, rate limiting, and WhatsApp webhook signature validation.
- Non-root container users and container health checks.
- Data services isolated on a private network (not published to the host).

### Known issues

- Voice-note confirmation state is held **in memory**; for multi-instance
  backends, back it with Redis (see [docs/performance.md](docs/performance.md)).
- The dashboard REST API ships **without built-in auth** — place it behind
  Supabase Auth or a gateway before exposing it (see [docs/security.md](docs/security.md)).
- **Database integration tests require a real PostgreSQL** (models use
  PostgreSQL-only types); they are skipped unless `ORCHESTRA_TEST_DATABASE_URL`
  is set.
- Project code allocation is sequential; use a DB sequence for high-concurrency
  creation.

### Migration guide

This is the initial `1.0.0` release, so there is **no migration from a previous
version**. For a fresh install, apply the canonical schema
(`orchestra/database/schema.sql`) or run the Alembic migration `001_initial_schema`,
then follow [DEPLOYMENT.md](DEPLOYMENT.md).

[1.0.0]: https://github.com/MUSTAQ-AHAMMAD/Mudir/releases/tag/v1.0.0
