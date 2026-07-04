# مدير · Mudir — AI Project Coordinator for WhatsApp

Mudir ("Manager" in Arabic) is a B2B AI project coordinator that lives **inside
WhatsApp**. It coordinates multi-team projects such as retail store openings:
teams (Property → Marketing → IT) complete sequential tasks while the bot tracks
progress, sends reminders, escalates delays, and confirms the store opens on time.

> Built for Saudi retail chains. All bot replies are **bilingual** — Arabic first,
> English fallback — and the schedule respects the Saudi working week (Sun–Thu).

---

## 🧭 Answers to the pre-build design questions

1. **Backend — Node.js or Python?** → **Node.js / Express** was chosen (the file
   layout in the brief used `.js`, and the Twilio + Supabase + OpenAI SDKs are
   first-class in Node). All backend code is in [`backend/`](backend/).
2. **Twilio sandbox or production?** → Start on the **Twilio WhatsApp Sandbox**
   for development (`TWILIO_WHATSAPP_FROM=whatsapp:+14155238886`), then switch to
   an approved production sender. Outbound business-initiated messages use the
   Meta-approved templates in [`WHATSAPP_TEMPLATES.md`](WHATSAPP_TEMPLATES.md).
3. **How many teams per store opening?** → Default **3** (Property, Marketing,
   IT), configurable via `DEFAULT_TEAM_COUNT` and per-project `metadata.workflow`
   (e.g. add Logistics). The state machine adapts to any workflow length.
4. **What if a team lead leaves the WhatsApp group?** → Notifications are sent to
   the team lead's stored WhatsApp number (from the `team_leads` table), **not**
   to group membership, so leaving the group does not break routing. Update the
   number on the Settings page; if a lead is unreachable, overdue tasks
   auto-escalate to the team's `escalation_number` (CEO).
5. **DMs or group chats?** → Both work. The bot responds to whatever number
   messages it (group or 1:1). Commands are keyed off the sender's team lead
   record, so a lead can drive their tasks from a DM or the group.

---

## 🏗️ Architecture

```
backend/                 Node.js/Express service (webhook + REST API + cron)
├── src/
│   ├── index.js         App entrypoint (Express, rate limiting, cron)
│   ├── webhook.js       Twilio WhatsApp webhook (signature verified) + router
│   ├── commands.js      /new_project /assign /complete /extend /status /escalate
│   ├── state-machine.js property → marketing → it → ready → completed
│   ├── database.js      Supabase data-access layer (repository interface)
│   ├── notifications.js Outbound WhatsApp via Twilio (retry/backoff)
│   ├── ai-service.js    OpenAI summaries + Whisper voice transcription
│   ├── voice-handler.js Voice note → intent → confirm → execute
│   ├── cron-jobs.js     09:00 daily summary; hourly overdue escalation; Fri skip
│   ├── templates.js     Bilingual (AR/EN) message copy
│   ├── api.js           JSON REST API for the dashboard
│   ├── config.js        Central env config (fail-fast in production)
│   └── logger.js        Structured logging (pino), secrets redacted
├── migrations/          SQL: 0001_init.sql (schema), 0002_seed.sql (demo data)
└── tests/               Jest: state machine, utils, e2e flow, voice, cron, load

frontend/                React + Vite + Tailwind admin dashboard
└── src/components/      Dashboard, ProjectTimeline, TeamOnboarding, Analytics, Settings
```

### State machine

```
property_pending → marketing_pending → it_pending → ready → completed
```

When a team runs `/complete`, the engine: (1) marks their tasks done,
(2) computes the next state, (3) persists it, (4) writes an audit log, and
(5) notifies the next team lead (or broadcasts readiness to everyone).

---

## 🚀 Getting started

### Prerequisites
- Node.js ≥ 18
- A Supabase project, a Twilio WhatsApp sender, and an OpenAI API key

### Backend
```bash
cd backend
cp .env.example .env          # fill in TWILIO_*, SUPABASE_*, OPENAI_*
npm install
# Apply the schema in the Supabase SQL editor:
#   migrations/0001_init.sql  then  migrations/0002_seed.sql
npm test                      # run the test suite
npm run dev                   # start on http://localhost:3000
```

Point your Twilio WhatsApp webhook at `POST https://<public-url>/webhook`
(use ngrok locally: `ngrok http 3000`, then set `PUBLIC_URL`).

### Frontend
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxies /api → backend)
npm run build                 # production build
```

---

## 💬 WhatsApp commands

| Command | Description |
| --- | --- |
| `/new_project [name]` | Create a project and start the first team's turn |
| `/assign [team] [task] [deadline]` | Assign a task (deadline `YYYY-MM-DD`) |
| `/complete [project_id]` | Complete the current team's tasks and advance |
| `/extend [project_id] [team] [days]` | Extend a team's deadlines; alert the CEO |
| `/status [project_id]` | Full project timeline report |
| `/escalate [project_id] [reason]` | Urgent alert to the escalation contact |
| `/help` | List commands |

Voice notes are transcribed (Whisper); phrases like "we're done / خلصنا" are
mapped to `/complete` and **confirmed** before executing.

---

## 🛡️ Production hardening included
- Twilio webhook **signature verification** (`X-Twilio-Signature`)
- **Rate limiting** on the public webhook
- **Retry with exponential backoff** for Twilio/OpenAI calls
- Structured **logging** with secret redaction
- **Fail-fast** config validation in production
- Non-root Docker image + healthcheck

## ⚠️ Known limitations / next steps
- Voice-note confirmations are stored in-memory; back with Redis for multi-instance.
- Project code allocation is sequential; add a DB sequence for high-concurrency creation.
- The dashboard REST API ships without auth — place it behind Supabase Auth / a gateway.

---

## 🚢 Deployment
- **Docker:** `./deploy.sh docker` (uses `docker-compose.yml`)
- **Render.com:** connect the repo — [`render.yaml`](render.yaml) is a blueprint
- **Railway.app:** `./deploy.sh railway` (uses [`railway.json`](railway.json))

Set all secret env vars in the platform dashboard (never commit `.env`).

---

## 🎨 App design prompts
Prompts for generating the visual assets (logo, chat mockups, dashboard, Gantt
timeline, mobile concept, interaction flow) live in
[`docs/VISUAL_PROMPTS.md`](docs/VISUAL_PROMPTS.md). Paste them into DALL·E,
Midjourney, or Stable Diffusion.
