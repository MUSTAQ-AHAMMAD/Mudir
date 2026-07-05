# ORCHESTRA WhatsApp Integration (Phase 4)

The `orchestra/whatsapp/` package connects the [orchestration
engine](../engine/README.md) to **WhatsApp Groups** via the
[WATI](https://www.wati.io) API. It provides the outbound transport, an inbound
webhook receiver, message handlers, bilingual templates, session management and
webhook middleware.

Everything is **async**, fully **type-hinted**, logs through the shared
`orchestra.services` logger, and imports heavy dependencies **lazily** so the
package stays cheap to import and easy to unit-test.

## Modules

| File                 | Purpose                                                        |
|----------------------|----------------------------------------------------------------|
| `config.py`          | Environment-sourced configuration (`WhatsAppConfig`)           |
| `exceptions.py`      | WhatsApp-specific exception hierarchy                          |
| `client.py`          | Async WATI API client — retries, rate limiting, pooling        |
| `sender.py`          | `WhatsAppSender` — implements the engine's transport protocol  |
| `webhook.py`         | WATI webhook receiver + HMAC-SHA256 signature validation       |
| `handlers.py`        | Per-type pre-processing (text/voice/image/document/…)          |
| `session_manager.py` | Group ↔ company/project session management                     |
| `middleware.py`      | Rate limit / auth / logging / error / timeout middleware       |
| `templates.py`       | Bilingual (Arabic + English) message templates                 |

## Quick start

```python
from orchestra.engine import get_orchestrator
from orchestra.whatsapp import WhatsAppSender, WhatsAppClient, templates

# 1. Wire the WhatsApp transport into the engine (implements the Phase 3
#    WhatsAppSender protocol used by TeamCoordinator/Orchestrator).
orchestrator = get_orchestrator(whatsapp_service=WhatsAppSender())

# 2. Send a message to a group.
client = WhatsAppClient()
await client.send_message("group123", "Test message")

# 3. Render a bilingual template.
text = templates.render(
    "PROJECT_CREATED",
    {"project_name": "Riyadh Mall", "team": "Property Team"},
    lang="ar",
)
```

## Inbound webhook

`webhook.py` is framework-agnostic. Mount it on any web framework using the
`WebhookReceiver.route_request` dispatcher:

```python
from orchestra.whatsapp import WebhookReceiver

receiver = WebhookReceiver()

# POST /webhook/wati  → routes messages into Orchestrator.handle_incoming_message
# GET  /webhook/health → webhook health endpoint
status, body = await receiver.route_request(
    "POST", "/webhook/wati",
    body=payload,          # decoded JSON
    raw_body=raw_bytes,    # for signature verification
    signature=request.headers.get("x-wati-signature"),
)
```

Signatures are validated with **HMAC-SHA256** over the raw request body using
`WEBHOOK_SECRET`.

## Configuration

All settings come from environment variables (see `WhatsAppConfig`):

```bash
WATI_API_URL=https://live-server.wati.io
WATI_API_KEY=your_api_key
WEBHOOK_SECRET=your_webhook_secret
WEBHOOK_URL=https://your-domain.com/webhook/wati

# Optional tuning
WHATSAPP_RATE_LIMIT_PER_GROUP=20
WHATSAPP_RATE_LIMIT_PER_USER=10
WHATSAPP_RATE_LIMIT_WINDOW=60
WHATSAPP_MEDIA_DOWNLOAD_TIMEOUT=60
WHATSAPP_TEMPLATE_NAMESPACE=
WHATSAPP_DEFAULT_LANG=ar
```

## Templates

Ten bilingual templates are provided (`PROJECT_CREATED`, `STAGE_COMPLETED`,
`STAGE_STARTED`, `TASK_ASSIGNED`, `DAILY_REMINDER`, `OVERDUE_ALERT`,
`ESCALATION`, `PROJECT_COMPLETE`, `WEEKLY_SUMMARY`, `HELP_RESPONSE`). Each has an
Arabic and English body; `render(name, vars, lang=...)` returns Arabic, English,
or both. The Meta/Twilio pre-approved versions live in
[`WHATSAPP_TEMPLATES.md`](../../WHATSAPP_TEMPLATES.md).

## Installation

```bash
pip install -r orchestra/whatsapp/requirements.txt
```

Only `httpx` is required for live API calls. Media pre-processing (OCR, PDF/DOCX
extraction) uses optional packages listed in `requirements.txt`; voice
transcription reuses the self-hosted Whisper service.

## Tests

The test suite uses the stdlib `unittest` and mocks the WATI API, so it runs
with no extra dependencies:

```bash
python -m unittest discover -s orchestra/whatsapp/tests
```

Coverage includes: mocked WATI responses, retry/backoff, rate limiting, webhook
signature validation, message routing, template rendering (Arabic + English)
and media download.
