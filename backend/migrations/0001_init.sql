-- =============================================================================
-- Mudir — initial schema (Supabase / PostgreSQL)
-- =============================================================================
-- Run with the Supabase SQL editor or `supabase db push`.
-- Tables: projects, tasks, team_leads, project_logs.
-- The project state machine flows:
--   property_pending -> marketing_pending -> it_pending -> ready -> completed
-- =============================================================================

-- Enable UUID generation (available by default on Supabase).
create extension if not exists "pgcrypto";

-- -----------------------------------------------------------------------------
-- team_leads: one row per team lead reachable over WhatsApp.
-- `escalation_number` is who to alert (e.g. CEO) when this team is blocked.
-- -----------------------------------------------------------------------------
create table if not exists team_leads (
  id                uuid primary key default gen_random_uuid(),
  team_name         text not null,
  whatsapp_number   text not null,
  escalation_number text,
  created_at        timestamptz not null default now(),
  unique (team_name, whatsapp_number)
);

-- -----------------------------------------------------------------------------
-- projects: the coordination unit (e.g. a single store opening).
-- `current_team` mirrors the state machine's active team for quick lookups.
-- `metadata` stores arbitrary structured data (JSONB) such as custom workflow.
-- -----------------------------------------------------------------------------
create table if not exists projects (
  id            uuid primary key default gen_random_uuid(),
  -- Human-friendly identifier used in WhatsApp commands, e.g. "P-001".
  code          text not null unique,
  name          text not null,
  status        text not null default 'property_pending'
                check (status in (
                  'property_pending',
                  'marketing_pending',
                  'it_pending',
                  'ready',
                  'completed'
                )),
  current_team  text,
  location      text,
  opening_date  date,
  metadata      jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- tasks: work items assigned to a team within a project.
-- -----------------------------------------------------------------------------
create table if not exists tasks (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references projects(id) on delete cascade,
  assigned_team  text not null,
  description    text not null,
  deadline       date,
  status         text not null default 'pending'
                 check (status in ('pending', 'in_progress', 'done', 'blocked')),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- project_logs: append-only audit trail of everything that happens.
-- -----------------------------------------------------------------------------
create table if not exists project_logs (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references projects(id) on delete cascade,
  message     text not null,
  created_at  timestamptz not null default now()
);

-- Helpful indexes for the most common queries.
create index if not exists idx_tasks_project      on tasks(project_id);
create index if not exists idx_tasks_status       on tasks(status);
create index if not exists idx_tasks_deadline     on tasks(deadline);
create index if not exists idx_logs_project        on project_logs(project_id);
create index if not exists idx_projects_status     on projects(status);

-- Keep `updated_at` fresh on any row change.
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_projects_updated on projects;
create trigger trg_projects_updated before update on projects
  for each row execute function set_updated_at();

drop trigger if exists trg_tasks_updated on tasks;
create trigger trg_tasks_updated before update on tasks
  for each row execute function set_updated_at();
