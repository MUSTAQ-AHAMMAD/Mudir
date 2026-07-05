# Security & Privacy — Mudir / ORCHESTRA

This document describes Mudir's security model, data-privacy posture, regulatory
compliance (PDPL/GDPR), hardening guidance and incident response.

---

## 1. Security model

**Trust boundaries**

- **Public edge (nginx):** the only internet-facing surface. Terminates TLS,
  enforces HTTP→HTTPS redirect + HSTS, applies rate limiting and security
  headers, and routes to the backend and frontend.
- **Application:** the Node backend and Python engine run on a private Docker
  network. They validate all inbound data.
- **Data & AI services:** PostgreSQL, Ollama, Whisper, ChromaDB and the ML models
  are **not published to the host** — they are reachable only over the internal
  compose network.

**Authentication & authorisation**

- **Webhook:** every inbound WhatsApp request is verified against the provider
  **signature** (`X-Twilio-Signature` / WATI secret, HMAC-SHA256). Invalid or
  missing signatures are rejected.
- **REST API:** must be placed behind **Supabase Auth** or a gateway in
  production. Apply least-privilege — only admins may edit teams, workflows and
  settings.
- **Bot identity:** team leads are recognised by their stored WhatsApp number, so
  routing does not depend on group membership.

**Input handling**

- Message content, media URLs and API payloads are validated before use.
- Media downloads are size-limited and (for voice notes) restricted to an
  allow-list of provider hosts to prevent SSRF.
- Database access uses parameterised queries via SQLAlchemy (no string-built
  SQL).

---

## 2. Data privacy

Mudir is **100% self-hosted**:

- Speech-to-text (Whisper), language understanding (Ollama), embeddings (BGE-M3),
  translation and sentiment (NLLB) all run **on your own server**.
- **No message content, transcript or project data is sent to OpenAI or any
  third-party AI provider.**
- All persistent data lives in **your** PostgreSQL (and ChromaDB for vectors).

**Data categories stored:** company/team configuration, WhatsApp numbers,
project/stage/task records, communication logs (message text/transcripts) and
learned workflows.

**Data minimisation:** collect only what coordination requires. Avoid placing
sensitive personal data in free-text messages; treat transcripts as personal data.

---

## 3. PDPL / GDPR compliance

Because you control the infrastructure, you are the data controller and can meet
key obligations:

- **Data residency:** host in-region (e.g. within Saudi Arabia for PDPL); data
  never leaves your servers.
- **Lawful basis & purpose limitation:** use data only for project coordination;
  document the basis.
- **Data-subject rights:** locate records by company + team-lead identifier to
  support access and erasure; delete through the database layer.
- **Retention:** define and enforce a retention/purge policy (e.g. remove closed
  projects and their logs after N months).
- **Records of processing:** keep an inventory of what is collected, why, and for
  how long.
- **Breach notification:** follow the incident-response process below and your
  regulator's timelines.

> This is operational guidance, not legal advice. Consult your DPO/counsel for a
> compliant configuration.

---

## 4. Security best practices

- Keep **all secrets** in `.env` (git-ignored) or a secrets manager — never in
  code or images. Rotate credentials regularly.
- **HTTPS only**; keep HSTS enabled and certificates auto-renewed.
- Keep **webhook signature verification enabled** in all environments.
- Run containers as **non-root** with health checks (as configured).
- **Patch** the host and rebuild images regularly to pick up base-image CVEs.
- Enable **encryption at rest** for PostgreSQL volumes (e.g. LUKS) and encrypted
  backups.
- Restrict network exposure: only ports **80/443** on the host; everything else
  stays internal.
- Enable **audit logging** (communication logs + structured backend logs with
  secret redaction) and ship them to a central store.
- Run the security tooling in CI (dependency advisories, secret scanning, and the
  code-scanning workflow) and act on findings.

---

## 5. Incident response

1. **Detect** — alerts from monitoring (see [performance.md](performance.md)),
   anomalous logs, or a report.
2. **Contain** — revoke/rotate affected credentials; block abusive senders at the
   edge; scale down or isolate compromised services.
3. **Eradicate** — patch the vulnerability, rebuild images, redeploy.
4. **Recover** — restore from a known-good backup (`scripts/backup.sh` /
   restore), verify integrity, resume service.
5. **Notify** — inform affected data subjects and regulators per PDPL/GDPR
   timelines where required.
6. **Learn** — write a post-mortem; add detections/tests to prevent recurrence.

Keep an up-to-date contact list (on-call, DPO, provider support) and rehearse the
restore procedure periodically.
