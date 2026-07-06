# API Reference — Mudir / ORCHESTRA

The backend (Node.js/Express) exposes two surfaces:

1. A **WhatsApp webhook** consumed by the messaging provider (WATI/Twilio).
2. A **REST API** under `/api` used by the admin dashboard.

Base URL in production: `https://<your-domain>` (all traffic terminates at nginx
over HTTPS). Internal service ports are not published to the host.

---

## Authentication

- **REST API (`/api/*`)** — the API ships without built-in auth for demo/dev.
  In production, place it behind **Supabase Auth** or an API gateway and pass a
  bearer token / session cookie from the dashboard. Do not expose `/api`
  publicly without auth.
- **Webhook (`/webhook`)** — authenticated by **provider signature**
  (`X-Twilio-Signature`, HMAC over the request), validated on every request.
  Requests with a missing/invalid signature are rejected.

---

## Rate limits

- The public `/webhook` endpoint is **rate-limited** at the application layer,
  and again at the nginx edge. Bursts beyond the limit receive `429 Too Many
  Requests`. Tune limits in the backend config and `nginx/nginx.conf`.

---

## REST endpoints

### `GET /health`
Liveness probe. No auth.

**200**
```json
{ "status": "ok", "service": "mudir", "env": "production" }
```

---

### `GET /api/projects`
List projects, optionally filtered by status.

| Query param | Type | Description |
| --- | --- | --- |
| `status` | string | Optional. e.g. `active`, `completed` |

**200**
```json
{
  "projects": [
    { "id": "…", "code": "P-1001", "name": "Riyadh Store", "status": "active",
      "current_stage": "Construction", "opening_date": "2026-08-01" }
  ]
}
```

---

### `GET /api/projects/:code`
Project detail with tasks and communication logs.

**200**
```json
{
  "project": { "id": "…", "code": "P-1001", "name": "Riyadh Store", "status": "active" },
  "tasks": [ { "id": "…", "title": "Pour foundation", "status": "done" } ],
  "logs":  [ { "id": "…", "direction": "outbound", "message": "Stage started" } ]
}
```

**404** `{ "error": "not_found" }`

---

### `GET /api/team-leads`
List team leads (used by the Settings page).

**200**
```json
{ "teamLeads": [ { "team_name": "Property", "whatsapp_number": "+9665…",
                   "escalation_number": "+9665…" } ] }
```

---

### `PUT /api/team-leads`
Create or update a team lead.

**Request**
```json
{ "team_name": "Property", "whatsapp_number": "+9665…", "escalation_number": "+9665…" }
```

**200** `{ "teamLead": { … } }`
**400** `{ "error": "team_name and whatsapp_number required" }`

---

### `GET /api/analytics`
Aggregate metrics for the Analytics page.

**200** (shape)
```json
{
  "avgCompletionDays": 42,
  "totalProjects": 12,
  "completedProjects": 7,
  "totalEscalations": 4,
  "escalationsByProject": { "P-1001": 2 }
}
```

---

## Webhook

### `POST /webhook`
Receives inbound WhatsApp events from the provider.

- **Auth:** provider signature header (validated; invalid → rejected).
- **Body:** provider-specific form/JSON payload containing the message type
  (`text`, `audio`/voice, `image`, …), sender, group id and content/media URL.
- **Behaviour:** the message is parsed (voice → Whisper transcription, image →
  OCR), intent is classified, the matching handler runs, and a bilingual reply is
  sent back through the provider's send API.
- **Response:** `200` on accepted events; the reply itself is delivered
  asynchronously via the provider.

Message types handled: text, voice/audio, image. Messages sent *by* the business
number (`from_me = true`) are ignored to prevent loops.

---

## Error codes

| HTTP | Body | Meaning |
| --- | --- | --- |
| `400` | `{ "error": "…" }` | Validation error (missing/invalid fields) |
| `401` / `403` | — | Missing/invalid auth or webhook signature |
| `404` | `{ "error": "not_found" }` | Resource does not exist |
| `429` | — | Rate limit exceeded |
| `500` | `{ "error": "internal_error" }` | Unexpected server error (logged) |

---

## SDK / client examples

**cURL**
```bash
TOKEN="your-api-token"
curl https://your-domain/api/projects?status=active \
  -H "Authorization: Token ${TOKEN}"
```

**JavaScript (fetch)**
```js
const token = "your-api-token";
const res = await fetch("https://your-domain/api/projects", {
  headers: { Authorization: `Token ${token}` },
});
const { projects } = await res.json();
```

**Python (requests)**
```python
import requests

token = "your-api-token"
r = requests.get(
    "https://your-domain/api/projects",
    headers={"Authorization": f"Token {token}"},
    timeout=30,
)
r.raise_for_status()
projects = r.json()["projects"]
```

> The Python engine (`orchestra/`) is normally driven through the webhook, not
> called directly. To embed it, construct an `Orchestrator`
> (`orchestra.engine.orchestrator.get_orchestrator`) and call
> `handle_incoming_message(text, sender, group_id)` — see
> [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).
