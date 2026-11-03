-- Read policies for members. The membership check lives in a private schema that the Data API
-- doesn't expose, so it can't be called as /rest/v1/rpc/is_member (flagged by Supabase's
-- security advisor when it was first placed in public).

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

create or replace function private.is_member(target_org uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.memberships m
    where m.org_id = target_org and m.user_id = (select auth.uid())
  );
$$;
revoke all on function private.is_member(uuid) from public, anon;
grant execute on function private.is_member(uuid) to authenticated;

create policy "members read their organizations" on public.organizations
  for select to authenticated using (private.is_member(id));
create policy "members read their workspace members" on public.memberships
  for select to authenticated using (private.is_member(org_id));
create policy "members read datasets" on public.datasets
  for select to authenticated using (private.is_member(org_id));
create policy "members read agents" on public.agents
  for select to authenticated using (private.is_member(org_id));
create policy "members read approvals" on public.approvals
  for select to authenticated using (private.is_member(org_id));
create policy "members read shadow runs" on public.shadow_runs
  for select to authenticated using (private.is_member(org_id));
create policy "members read actions" on public.actions
  for select to authenticated using (private.is_member(org_id));
create policy "members read notifications" on public.notifications
  for select to authenticated using (private.is_member(org_id));

-- Deny-by-default tables, stated so the intent is recorded: token material never reaches a browser.
comment on table public.invitations is 'No client policies on purpose: holds invite token hashes; API-only.';
comment on table public.connections is 'No client policies on purpose: holds encrypted OAuth refresh tokens; API-only.';
