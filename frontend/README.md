# مدير · Mudir — Admin Dashboard (Frontend)

React + Vite + Tailwind CSS admin dashboard for the Mudir AI Project
Coordinator. Arabic-first (RTL) with light/dark themes, real-time updates and
Chart.js visualisations.

## ✨ Features

- **8 pages**: Dashboard, Projects, Project Detail, Workflows, Teams, Analytics,
  Settings, WhatsApp Settings.
- **Arabic-first / RTL** with an in-app Arabic ⇄ English toggle and dark mode.
- **Brand design**: deep green `#0d5c36`, gold `#d4af37`, subtle Saudi geometric
  pattern; responsive for desktop/tablet/mobile; WCAG 2.1 AA focus states.
- **Supabase** auth (email/password + Google) and real-time subscriptions.
- **React Query** for server state, **Context API** for global UI state,
  **React Hook Form** for forms, **Chart.js** for charts.
- Graceful **REST fallback**: when Supabase env vars are absent, the app talks to
  the existing Node backend at `/api` and runs in a permissive demo auth mode.

## 📸 Screenshots

See the [screenshot gallery](../docs/screenshots/README.md) for real captures of
every page (Dashboard, Projects, Project Detail, Workflows, Teams, Analytics,
Settings, WhatsApp) in light/dark themes and Arabic (RTL) / English (LTR).

## 🚀 Getting started

```bash
cd frontend
cp .env.example .env      # fill in Supabase + API values (optional for demo)
npm install
npm run dev               # http://localhost:5173 (proxies /api → backend)
npm run build             # production build → dist/
npm test                  # run the Vitest suite
```

### Environment variables

| Variable                  | Purpose                                             |
| ------------------------- | --------------------------------------------------- |
| `VITE_SUPABASE_URL`       | Supabase project URL (enables auth + realtime)      |
| `VITE_SUPABASE_ANON_KEY`  | Supabase anon/public key                            |
| `VITE_API_URL`            | Backend REST base URL (default same-origin `/api`)  |
| `VITE_WHATSAPP_GROUP_ID`  | Default WhatsApp test group id                       |

> When `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` are omitted, the dashboard
> runs in **demo mode**: any login works and data is read from the REST API.

## 🗂️ Structure

```
src/
├── api/         Supabase client + data modules (projects, teams, workflows, analytics, settings)
├── components/  Reusable UI (ProjectCard, StatusBadge, ProgressBar, StageTimeline,
│                AISuggestionCard, TeamMember, SearchFilter, Pagination, Modal, Toast,
│                Loading, Sidebar, Header, StatCard, Chart)
├── context/     Global state (AppContext, AuthContext, ThemeContext)
├── hooks/       Data + state hooks (useProjects, useTeams, useWorkflows, useAnalytics,
│                useWebSocket, useNotifications, useAuth)
├── pages/       Route pages (Dashboard, Projects, ProjectDetail, Workflows, Teams,
│                Analytics, Settings, WhatsAppSettings, Login)
├── styles/      Tailwind entry (index.css) + theme tokens (themes.js)
├── utils/       Helpers (date, status, validators, export, colors, formatting)
└── test/        Vitest setup + provider render helper
```

## 🧩 Routes

| Path            | Page                    |
| --------------- | ----------------------- |
| `/`             | Dashboard               |
| `/projects`     | Projects list           |
| `/projects/:id` | Project detail (by code)|
| `/workflows`    | Workflow management     |
| `/teams`        | Team management         |
| `/analytics`    | Analytics & insights    |
| `/settings`     | System settings         |
| `/whatsapp`     | WhatsApp integration    |

## 🎨 Theming & i18n

- `ThemeContext` toggles the `dark` class and the `dir`/`lang` attributes on
  `<html>`, so Tailwind's `dark:` variant and RTL layout apply app-wide.
- Bilingual labels live in `utils/status.js` and are formatted via the `Intl`
  APIs in `utils/date.js` and `utils/formatting.js` (no i18n dependency).

## 🧪 Testing

Unit tests (utils) and component tests (Vitest + Testing Library) live next to
the code they cover (`*.test.js` / `*.test.jsx`). Run `npm test`.
