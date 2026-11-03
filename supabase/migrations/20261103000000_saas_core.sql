-- ShadowCost SaaS core: workspaces (organizations), members and roles, datasets, agents,
-- approvals, shadow runs, the approval queue, connectors, notifications and sales leads.
-- Every table has row-level security on. The API writes with the secret key (which bypasses
-- RLS) after checking membership itself; signed-in members may only read their own workspace.
-- Applied to project jyixkprzmihvuanprfdm on 2026-11-03.

create extension if not exists pgcrypto;

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 1 and 80),
  created_by uuid not null references auth.users(id) on delete restrict,
  plan text not null default 'free' check (plan in ('free', 'starter', 'growth')),
  stripe_customer_id text unique,
  stripe_subscription_id text unique,
  subscription_status text,
  current_period_end timestamptz,
  created_at timestamptz not null default now()
);

create table public.memberships (
  org_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  email text not null,
  role text not null check (role in ('owner', 'admin', 'approver', 'viewer')),
  created_at timestamptz not null default now(),
  primary key (org_id, user_id)
);
create index memberships_user_idx on public.memberships(user_id);

create table public.invitations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  email text not null,
  role text not null check (role in ('admin', 'approver', 'viewer')),
  token_hash text not null unique,
  invited_by uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '7 days',
  accepted_at timestamptz
);
create index invitations_org_idx on public.invitations(org_id);

create table public.datasets (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  name text not null,
  source text not null check (source in ('upload', 'google')),
  storage_prefix text not null,
  status text not null default 'ready' check (status in ('processing', 'ready', 'error')),
  summary jsonb,
  error text,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);
create index datasets_org_idx on public.datasets(org_id);

create table public.agents (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  dataset_id uuid references public.datasets(id) on delete set null,
  workflow_id text not null,
  name text not null,
  spec jsonb not null,
  spec_hash text not null,
  evaluation jsonb,
  created_at timestamptz not null default now(),
  unique (org_id, spec_hash)
);
create index agents_org_idx on public.agents(org_id);

create table public.approvals (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  agent_id uuid not null references public.agents(id) on delete cascade,
  spec_hash text not null,
  approved_by uuid not null references auth.users(id) on delete cascade,
  approved_email text not null,
  approved_at timestamptz not null default now(),
  unique (agent_id, spec_hash)
);

create table public.shadow_runs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  agent_id uuid not null references public.agents(id) on delete cascade,
  dataset_id uuid references public.datasets(id) on delete set null,
  final_stage text not null,
  minutes_saved double precision not null,
  result jsonb not null,
  created_at timestamptz not null default now()
);
create index shadow_runs_agent_idx on public.shadow_runs(agent_id, created_at desc);

create table public.actions (
  id bigint generated always as identity primary key,
  org_id uuid not null references public.organizations(id) on delete cascade,
  agent_id uuid not null references public.agents(id) on delete cascade,
  case_id text not null,
  day date not null,
  proposal jsonb not null,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected', 'applied')),
  decided_by uuid references auth.users(id) on delete set null,
  decided_email text,
  decided_at timestamptz,
  created_at timestamptz not null default now()
);
create index actions_org_status_idx on public.actions(org_id, status);

create table public.connections (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  provider text not null check (provider in ('google')),
  account_email text,
  scopes text[] not null default '{}',
  refresh_token_encrypted text not null,
  settings jsonb not null default '{}'::jsonb,
  last_synced_at timestamptz,
  last_error text,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (org_id, provider)
);

create table public.notifications (
  id bigint generated always as identity primary key,
  org_id uuid not null references public.organizations(id) on delete cascade,
  kind text not null,
  subject text not null,
  recipients text[] not null,
  delivered boolean not null default false,
  created_at timestamptz not null default now()
);
create index notifications_org_idx on public.notifications(org_id, created_at desc);

create table public.leads (
  id bigint generated always as identity primary key,
  name text not null check (char_length(name) between 1 and 120),
  email text not null check (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$' and char_length(email) <= 254),
  company text check (char_length(company) <= 120),
  team_size text check (char_length(team_size) <= 40),
  message text check (char_length(message) <= 2000),
  created_at timestamptz not null default now()
);

alter table public.organizations enable row level security;
alter table public.memberships enable row level security;
alter table public.invitations enable row level security;
alter table public.datasets enable row level security;
alter table public.agents enable row level security;
alter table public.approvals enable row level security;
alter table public.shadow_runs enable row level security;
alter table public.actions enable row level security;
alter table public.connections enable row level security;
alter table public.notifications enable row level security;
alter table public.leads enable row level security;

-- Anyone may submit the demo form; nobody may read leads from the browser.
create policy "anyone can request a demo" on public.leads
  for insert to anon, authenticated with check (true);

-- Private bucket for uploaded and synced files; only the API (secret key) touches it.
insert into storage.buckets (id, name, public, file_size_limit)
values ('datasets', 'datasets', false, 52428800)
on conflict (id) do nothing;
