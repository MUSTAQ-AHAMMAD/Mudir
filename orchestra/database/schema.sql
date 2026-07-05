-- =============================================================================
-- ORCHESTRA — database schema (Supabase / PostgreSQL)
-- =============================================================================
-- Complete schema for the ORCHESTRA coordination platform. It mirrors the
-- SQLAlchemy models in `orchestra/database/models.py`.
--
-- Apply with the Supabase SQL editor, `supabase db push`, or:
--     psql "$DATABASE_URL" -f orchestra/database/schema.sql
--
-- Features:
--   * Multi-tenancy   — every domain table is scoped to a company_id.
--   * Soft deletes    — is_active flag on mutable tables.
--   * Audit trail     — append-only communication_logs.
--   * Flexible data   — JSONB metadata columns.
--   * Row Level Security policies for tenant isolation.
-- =============================================================================

-- gen_random_uuid() is available by default on Supabase.
create extension if not exists "pgcrypto";

-- -----------------------------------------------------------------------------
-- Enum types
-- -----------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_type where typname = 'project_status') then
    create type project_status as enum
      ('draft', 'active', 'on_hold', 'blocked', 'completed', 'cancelled');
  end if;
  if not exists (select 1 from pg_type where typname = 'stage_status') then
    create type stage_status as enum
      ('pending', 'in_progress', 'completed', 'skipped', 'blocked');
  end if;
  if not exists (select 1 from pg_type where typname = 'task_status') then
    create type task_status as enum
      ('pending', 'in_progress', 'done', 'blocked', 'cancelled');
  end if;
  if not exists (select 1 from pg_type where typname = 'escalation_priority') then
    create type escalation_priority as enum
      ('low', 'medium', 'high', 'critical');
  end if;
  if not exists (select 1 from pg_type where typname = 'escalation_status') then
    create type escalation_status as enum
      ('pending', 'acknowledged', 'resolved', 'dismissed');
  end if;
  if not exists (select 1 from pg_type where typname = 'message_direction') then
    create type message_direction as enum
      ('inbound', 'outbound', 'system');
  end if;
  if not exists (select 1 from pg_type where typname = 'webhook_status') then
    create type webhook_status as enum
      ('pending', 'active', 'failed', 'disabled');
  end if;
end$$;

-- -----------------------------------------------------------------------------
-- companies: the tenant. Everything else is scoped to a company.
-- -----------------------------------------------------------------------------
create table if not exists companies (
  id              uuid primary key default gen_random_uuid(),
  name            text not null,
  slug            text not null unique,
  whatsapp_number text,
  timezone        text not null default 'Asia/Riyadh',
  metadata        jsonb not null default '{}'::jsonb,
  is_active       boolean not null default true,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index if not exists idx_companies_slug on companies (slug);

-- -----------------------------------------------------------------------------
-- workflows: reusable, AI-learned stage templates for a kind of project.
-- -----------------------------------------------------------------------------
create table if not exists workflows (
  id           uuid primary key default gen_random_uuid(),
  company_id   uuid not null references companies (id) on delete cascade,
  name         text not null,
  description  text,
  stages       jsonb not null default '[]'::jsonb,
  confidence   double precision not null default 0,
  usage_count  integer not null default 0,
  metadata     jsonb not null default '{}'::jsonb,
  is_active    boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint uq_workflows_company_name unique (company_id, name),
  constraint ck_workflows_confidence_range check (confidence >= 0 and confidence <= 1)
);
create index if not exists idx_workflows_company_id on workflows (company_id);
create index if not exists idx_workflows_confidence on workflows (confidence);

-- -----------------------------------------------------------------------------
-- projects: the coordination unit (e.g. a single store opening).
-- -----------------------------------------------------------------------------
create table if not exists projects (
  id            uuid primary key default gen_random_uuid(),
  company_id    uuid not null references companies (id) on delete cascade,
  workflow_id   uuid references workflows (id) on delete set null,
  code          text,
  name          text not null,
  description   text,
  status        project_status not null default 'draft',
  current_stage text,
  location      text,
  opening_date  date,
  metadata      jsonb not null default '{}'::jsonb,
  is_active     boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint uq_projects_company_code unique (company_id, code)
);
create index if not exists idx_projects_status      on projects (status);
create index if not exists idx_projects_company_id  on projects (company_id);
create index if not exists idx_projects_workflow_id on projects (workflow_id);

-- -----------------------------------------------------------------------------
-- teams: a team reachable over WhatsApp, with a lead and JSON members.
-- -----------------------------------------------------------------------------
create table if not exists teams (
  id                uuid primary key default gen_random_uuid(),
  company_id        uuid not null references companies (id) on delete cascade,
  name              text not null,
  lead_name         text,
  lead_whatsapp     text,
  escalation_number text,
  members           jsonb not null default '[]'::jsonb,
  metadata          jsonb not null default '{}'::jsonb,
  is_active         boolean not null default true,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint uq_teams_company_name unique (company_id, name)
);
create index if not exists idx_teams_company_id    on teams (company_id);
create index if not exists idx_teams_lead_whatsapp on teams (lead_whatsapp);

-- -----------------------------------------------------------------------------
-- project_stages: a single stage within a project's workflow instance.
-- -----------------------------------------------------------------------------
create table if not exists project_stages (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references projects (id) on delete cascade,
  team_id      uuid references teams (id) on delete set null,
  name         text not null,
  description  text,
  sequence     integer not null default 0,
  status       stage_status not null default 'pending',
  started_at   timestamptz,
  completed_at timestamptz,
  metadata     jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists idx_project_stages_project_id on project_stages (project_id);
create index if not exists idx_project_stages_status     on project_stages (status);

-- -----------------------------------------------------------------------------
-- tasks: a work item within a project, optionally owned by a team/stage.
-- -----------------------------------------------------------------------------
create table if not exists tasks (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references projects (id) on delete cascade,
  team_id      uuid references teams (id) on delete set null,
  stage_id     uuid references project_stages (id) on delete set null,
  title        text not null,
  description  text,
  assigned_to  text,
  status       task_status not null default 'pending',
  deadline     date,
  completed_at timestamptz,
  metadata     jsonb not null default '{}'::jsonb,
  is_active    boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists idx_tasks_status     on tasks (status);
create index if not exists idx_tasks_project_id on tasks (project_id);
create index if not exists idx_tasks_team_id    on tasks (team_id);
create index if not exists idx_tasks_deadline   on tasks (deadline);

-- -----------------------------------------------------------------------------
-- escalations: a raised blocker needing attention from a lead / manager.
-- -----------------------------------------------------------------------------
create table if not exists escalations (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references projects (id) on delete cascade,
  task_id     uuid references tasks (id) on delete set null,
  reason      text not null,
  priority    escalation_priority not null default 'medium',
  status      escalation_status not null default 'pending',
  raised_to   text,
  resolution  text,
  resolved_at timestamptz,
  metadata    jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists idx_escalations_project_id on escalations (project_id);
create index if not exists idx_escalations_status     on escalations (status);
create index if not exists idx_escalations_priority   on escalations (priority);

-- -----------------------------------------------------------------------------
-- communication_logs: append-only audit trail of every message.
-- -----------------------------------------------------------------------------
create table if not exists communication_logs (
  id           uuid primary key default gen_random_uuid(),
  company_id   uuid not null references companies (id) on delete cascade,
  project_id   uuid references projects (id) on delete set null,
  direction    message_direction not null default 'inbound',
  channel      text not null default 'whatsapp',
  message_type text not null default 'text',
  sender       text,
  recipient    text,
  content      text,
  metadata     jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now()
);
create index if not exists idx_communication_logs_created_at on communication_logs (created_at);
create index if not exists idx_communication_logs_company_id on communication_logs (company_id);
create index if not exists idx_communication_logs_project_id on communication_logs (project_id);
create index if not exists idx_communication_logs_sender     on communication_logs (sender);

-- -----------------------------------------------------------------------------
-- learning_data: AI observations, learned patterns and suggestions.
-- -----------------------------------------------------------------------------
create table if not exists learning_data (
  id               uuid primary key default gen_random_uuid(),
  company_id       uuid references companies (id) on delete cascade,
  observation_type text not null,
  content          jsonb not null default '{}'::jsonb,
  suggestion       text,
  confidence       double precision not null default 0,
  is_implemented   boolean not null default false,
  implemented_at   timestamptz,
  metadata         jsonb not null default '{}'::jsonb,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint ck_learning_confidence_range check (confidence >= 0 and confidence <= 1)
);
create index if not exists idx_learning_data_confidence on learning_data (confidence);
create index if not exists idx_learning_data_company_id on learning_data (company_id);
create index if not exists idx_learning_data_type       on learning_data (observation_type);

-- -----------------------------------------------------------------------------
-- whatsapp_sessions: a WhatsApp group mapped to a company.
-- -----------------------------------------------------------------------------
create table if not exists whatsapp_sessions (
  id             uuid primary key default gen_random_uuid(),
  company_id     uuid not null references companies (id) on delete cascade,
  group_id       text not null unique,
  group_name     text,
  phone_number   text,
  webhook_status webhook_status not null default 'pending',
  session_data   jsonb not null default '{}'::jsonb,
  metadata       jsonb not null default '{}'::jsonb,
  is_active      boolean not null default true,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index if not exists idx_whatsapp_sessions_company_id on whatsapp_sessions (company_id);
create index if not exists idx_whatsapp_sessions_group_id   on whatsapp_sessions (group_id);

-- -----------------------------------------------------------------------------
-- model_cache: cache of AI model outputs keyed by an input hash, with expiry.
-- -----------------------------------------------------------------------------
create table if not exists model_cache (
  id         uuid primary key default gen_random_uuid(),
  cache_key  text not null unique,
  model_name text,
  input_hash text,
  output     jsonb not null default '{}'::jsonb,
  hits       integer not null default 0,
  created_at timestamptz not null default now(),
  expires_at timestamptz
);
create index if not exists idx_model_cache_cache_key  on model_cache (cache_key);
create index if not exists idx_model_cache_expires_at on model_cache (expires_at);

-- =============================================================================
-- updated_at maintenance
-- =============================================================================
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

do $$
declare
  tbl text;
begin
  foreach tbl in array array[
    'companies', 'workflows', 'projects', 'teams', 'project_stages',
    'tasks', 'escalations', 'learning_data', 'whatsapp_sessions'
  ]
  loop
    execute format('drop trigger if exists trg_%1$s_updated on %1$s;', tbl);
    execute format(
      'create trigger trg_%1$s_updated before update on %1$s
         for each row execute function set_updated_at();', tbl);
  end loop;
end$$;

-- =============================================================================
-- Row Level Security (multi-tenancy)
-- =============================================================================
-- Tenants are isolated by company_id. Requests should set the tenant via:
--     select set_config('app.current_company_id', '<uuid>', false);
-- The service-role key (used by the backend) bypasses RLS entirely.
--
-- The helper below returns the current tenant, or NULL when unset.
create or replace function current_company_id()
returns uuid as $$
  select nullif(current_setting('app.current_company_id', true), '')::uuid;
$$ language sql stable;

-- Enable RLS on every tenant-scoped table.
alter table companies          enable row level security;
alter table workflows          enable row level security;
alter table projects           enable row level security;
alter table teams              enable row level security;
alter table project_stages     enable row level security;
alter table tasks              enable row level security;
alter table escalations        enable row level security;
alter table communication_logs enable row level security;
alter table learning_data      enable row level security;
alter table whatsapp_sessions  enable row level security;

-- companies: a tenant may only see its own row.
drop policy if exists tenant_isolation_companies on companies;
create policy tenant_isolation_companies on companies
  using (id = current_company_id());

-- Directly-scoped tables (own company_id column).
drop policy if exists tenant_isolation_workflows on workflows;
create policy tenant_isolation_workflows on workflows
  using (company_id = current_company_id());

drop policy if exists tenant_isolation_projects on projects;
create policy tenant_isolation_projects on projects
  using (company_id = current_company_id());

drop policy if exists tenant_isolation_teams on teams;
create policy tenant_isolation_teams on teams
  using (company_id = current_company_id());

drop policy if exists tenant_isolation_communication_logs on communication_logs;
create policy tenant_isolation_communication_logs on communication_logs
  using (company_id = current_company_id());

drop policy if exists tenant_isolation_whatsapp_sessions on whatsapp_sessions;
create policy tenant_isolation_whatsapp_sessions on whatsapp_sessions
  using (company_id = current_company_id());

-- learning_data may be global (company_id null) or tenant-scoped.
drop policy if exists tenant_isolation_learning_data on learning_data;
create policy tenant_isolation_learning_data on learning_data
  using (company_id is null or company_id = current_company_id());

-- Indirectly-scoped tables (scoped through their parent project).
drop policy if exists tenant_isolation_project_stages on project_stages;
create policy tenant_isolation_project_stages on project_stages
  using (exists (
    select 1 from projects p
    where p.id = project_stages.project_id
      and p.company_id = current_company_id()
  ));

drop policy if exists tenant_isolation_tasks on tasks;
create policy tenant_isolation_tasks on tasks
  using (exists (
    select 1 from projects p
    where p.id = tasks.project_id
      and p.company_id = current_company_id()
  ));

drop policy if exists tenant_isolation_escalations on escalations;
create policy tenant_isolation_escalations on escalations
  using (exists (
    select 1 from projects p
    where p.id = escalations.project_id
      and p.company_id = current_company_id()
  ));

-- =============================================================================
-- Realtime (Supabase)
-- =============================================================================
-- Add tables to the supabase_realtime publication so clients can subscribe.
-- Wrapped so it is safe to run when the publication does not exist.
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table
      projects, tasks, escalations, communication_logs;
  end if;
exception
  when duplicate_object then null;
end$$;
