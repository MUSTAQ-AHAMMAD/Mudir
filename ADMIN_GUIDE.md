# Admin Guide — Mudir / ORCHESTRA

**Audience:** company administrators who configure teams, workflows and settings,
and who monitor projects from the dashboard.

---

## 1. Company setup

Each **company** is an isolated tenant — all workflows, projects, teams and
messages are scoped to it. A company record holds:

- **Name** and **slug** (unique identifier)
- **WhatsApp number** (the business sender)
- **Timezone** (defaults to `Asia/Riyadh`)
- Free-form **metadata** (e.g. default team count, business rules)

Create the first company by seeding the database (see
[`orchestra/database/schema.sql`](orchestra/database/schema.sql) and the seed
migration) or through the dashboard once authenticated.

---

## 2. Team management

Teams are reachable over WhatsApp and each has a lead:

| Field | Purpose |
| --- | --- |
| **Name** | e.g. Property, Marketing, IT, Logistics |
| **Lead name** | Display name of the responsible person |
| **Lead WhatsApp** | Number the bot notifies (routing is by number, not group membership) |
| **Escalation number** | Where overdue/urgent items go (usually the CEO) |
| **Members** | Optional list of `{name, whatsapp, role}` |

Manage teams from the dashboard **Settings / Teams** pages, or via the REST API
(`GET/PUT /api/team-leads`). Keep numbers current — this is the single most common
cause of missed notifications.

---

## 3. Workflow configuration

A **workflow** is an ordered list of stages for a kind of project. Mudir can
**learn** a workflow automatically from a conversation, or you can define one
explicitly. Each stage has:

- `name`, `description`
- `owner` (a team)
- `depends_on` (list of prerequisite stage names — supports parallel branches)

Workflows carry a **confidence** score (0–1) and a **usage count**. High-confidence,
frequently-used workflows are reused across new projects. Review learned
workflows on the **Workflows** page before relying on them.

> Because workflows are data (not code), Mudir supports **any industry** — retail
> store openings, software launches, event planning, construction — with no
> code changes.

---

## 4. Dashboard walkthrough

The admin dashboard (React + Vite, Arabic-first RTL, dark mode) provides:

- **Dashboard** — at-a-glance KPIs and active projects
- **Projects / Project detail** — timeline, stages, tasks, communication log
- **Workflows** — learned/defined workflows, confidence and usage
- **Teams** — team leads and escalation contacts
- **Analytics** — completion times, escalations, throughput (Chart.js)
- **Settings / WhatsApp Settings** — provider config, team leads
- **Login** — Supabase auth (with a REST fallback for demo mode)

See [`frontend/README.md`](frontend/README.md) for running the dashboard.

---

## 5. Analytics interpretation

- **Average completion time** — mean days from project creation to opening date
  across completed projects. Rising values suggest bottlenecks upstream.
- **Escalations per project** — counted from the communication log; a spike on a
  particular stage points to a recurring blocker to fix in the workflow.
- **Throughput** — projects completed per period; use it for capacity planning.

Investigate outliers on the Project detail page, where the full stage timeline
and message history explain *why* a project stalled.

---

## 6. AI learning management

- New workflows start with **lower confidence**; confidence and usage grow as the
  workflow is reused successfully.
- Review AI-learned workflows before trusting them for critical projects; edit or
  merge near-duplicates.
- The engine can **suggest optimisations** (reordering, merging, parallelising
  stages) — treat these as recommendations, not automatic changes.
- All AI runs **locally** (Ollama/Whisper/BGE-M3/NLLB); no external model calls.

---

## 7. User management

- **Team leads** are the primary "users" from the bot's perspective, identified by
  WhatsApp number.
- **Dashboard users** authenticate via Supabase Auth. Restrict who can view/edit
  by placing the REST API behind auth/a gateway (see security notes).
- Follow least-privilege: only admins should edit teams, workflows and settings.

---

## 8. Billing / usage

Mudir is **self-hosted and open-source (MIT)** — there are no per-message or
per-token fees. Your operating cost is the server (CPU/GPU), storage and
bandwidth. Track resource usage with the optional Prometheus + Grafana monitoring
stack (see [DEPLOYMENT.md](DEPLOYMENT.md) §3) and [docs/performance.md](docs/performance.md)
for sizing guidance.

---

## 9. Compliance (PDPL / GDPR)

Because everything runs on infrastructure you control:

- **Data residency** — messages, transcripts and project data stay in your own
  PostgreSQL; nothing is sent to third-party AI providers.
- **Lawful basis & minimisation** — collect only what coordination requires; avoid
  storing sensitive personal data in free-text fields.
- **Data-subject rights** — support access/erasure by locating records via the
  company + team-lead identifiers and deleting through the database layer.
- **Retention** — define and enforce a retention policy (e.g. purge closed
  projects after N months) and document it.
- **Security** — see [docs/security.md](docs/security.md) for encryption, access
  control and incident response.

For full details on the security model and privacy posture, read
[docs/security.md](docs/security.md).
