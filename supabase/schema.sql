-- PlantMind control plane. Safe to re-run: every statement is idempotent.
-- Run in the Supabase SQL editor (Dashboard -> SQL Editor -> New query -> Run).
--
-- The knowledge graph lives in neo4j and is shared by the plant. Everything
-- here is per-person: who someone is, and what they have asked. That split is
-- why this is in supabase rather than behind the gateway - the gateway serves
-- the brain and stays stateless, and row-level security does the tenancy.

-- ---------------------------------------------------------------- profiles
-- Who the engineer is, in the terms a plant actually uses. The unit and
-- projects are not decoration: they are the context that decides which alerts
-- and which corner of the graph matter to this person.
--
-- app_role drives both the frontend (which nav items are visible) and the
-- gateway (which endpoints are callable). The tiers:
--   worker    - Field Copilot only (mobile field persona, its own /field shell)
--   operator  - Ask, Alerts, Documents read  (default for every new signup)
--   planner   - + Connectors read
--   engineer  - + Graph, Compliance, MoC, Interview, document upload
--   admin     - full access + Connectors write, role management
--
-- 'worker' is a separate persona, not a privilege tier: it is provisioned
-- deliberately (field job titles below, or an admin setting it), never the
-- default a missing role falls back to.
--
-- NOTE: app_role is NOT given an inline CHECK in CREATE TABLE.
-- The DO block below owns the constraint so there is only ever one copy,
-- whether the table is brand-new or being migrated from an older version.
create table if not exists public.profiles (
    id           uuid primary key references auth.users on delete cascade,
    full_name    text,
    employee_id  text,
    job_title    text,
    department   text,
    plant        text,
    home_unit    text,
    projects     text[]      not null default '{}',
    expertise    text[]      not null default '{}',
    app_role     text        not null default 'operator',
    updated_at   timestamptz not null default now()
);

-- Migration: add app_role to tables that existed before this column.
-- IF NOT EXISTS is a no-op when the column is already present.
alter table public.profiles
    add column if not exists app_role text not null default 'operator';

-- Idempotent CHECK constraint. Lives here (not inline in CREATE TABLE) so
-- re-running the file never creates a duplicate constraint.
do $$
begin
    if not exists (
        select 1 from pg_constraint
         where conname = 'profiles_app_role_check'
           and conrelid = 'public.profiles'::regclass
    ) then
        alter table public.profiles
            add constraint profiles_app_role_check
            check (app_role in ('worker','operator','planner','engineer','admin'));
    end if;
end;
$$;

-- Migration: widen the CHECK to admit 'worker' on databases where the
-- constraint already exists with the older four-role definition. The guard
-- above only ADDS a missing constraint; it never alters an existing one, so
-- this drop-and-recreate is what actually lets 'worker' through on upgrade.
do $$
begin
    if exists (
        select 1 from pg_constraint
         where conname = 'profiles_app_role_check'
           and conrelid = 'public.profiles'::regclass
           and pg_get_constraintdef(oid) not like '%worker%'
    ) then
        alter table public.profiles drop constraint profiles_app_role_check;
        alter table public.profiles
            add constraint profiles_app_role_check
            check (app_role in ('worker','operator','planner','engineer','admin'));
    end if;
end;
$$;

alter table public.profiles enable row level security;

drop policy if exists "profiles are private to their owner" on public.profiles;
create policy "profiles are private to their owner"
    on public.profiles for all
    using  (auth.uid() = id)
    with check (auth.uid() = id);

-- Admins can read every profile (needed for the user-management page).
-- Check the JWT claim rather than querying the table to avoid infinite recursion!
drop policy if exists "admins can read all profiles" on public.profiles;
create policy "admins can read all profiles"
    on public.profiles for select
    using (
        (auth.jwt() -> 'app_metadata' ->> 'app_role') = 'admin'
    );

-- ---------------------------------------------------- handle_new_user trigger
-- Creates a profile row the moment someone signs up. Must never fail — any
-- exception here rolls back the entire auth transaction and returns a 500.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
    job_t text;
    mapped_role text := 'operator';
begin
    job_t := nullif(new.raw_user_meta_data ->> 'job_title', '');

    -- Map job title to app role automatically. Order matters: the field-worker
    -- titles are checked first so a "Field Technician" does not fall through to
    -- some broader match. Engineers/planners/managers keep the console; the
    -- hands-on field trades get the mobile Field Copilot persona instead.
    if job_t ilike '%worker%' or job_t ilike '%technician%' or job_t ilike '%fitter%'
       or job_t ilike '%mechanic%' or job_t ilike '%field oper%'
       or job_t ilike '%operative%' or job_t ilike '%rigger%'
       or job_t ilike '%electrician%' or job_t ilike '%welder%' then
        mapped_role := 'worker';
    elsif job_t ilike '%engineer%' or job_t ilike '%engg%' then
        mapped_role := 'engineer';
    elsif job_t ilike '%planner%' or job_t ilike '%scheduler%' then
        mapped_role := 'planner';
    elsif job_t ilike '%manager%' or job_t ilike '%admin%' or job_t ilike '%director%' then
        mapped_role := 'admin';
    end if;

    insert into public.profiles (id, full_name, job_title, department,
                                 plant, home_unit, app_role)
    values (new.id,
            coalesce(new.raw_user_meta_data ->> 'full_name',
                     split_part(new.email, '@', 1)),
            job_t,
            nullif(new.raw_user_meta_data ->> 'department', ''),
            nullif(new.raw_user_meta_data ->> 'plant',      ''),
            nullif(new.raw_user_meta_data ->> 'home_unit',  ''),
            mapped_role)
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- Backfill anyone who signed up before this trigger was installed.
insert into public.profiles (id, full_name)
select u.id, split_part(u.email, '@', 1)
  from auth.users u
on conflict (id) do nothing;

-- -------------------------------------------------- custom_jwt_claims hook
-- Stamps app_role into every Supabase access token so the gateway and the
-- frontend can make role decisions from the JWT alone, without a DB round-trip.
--
-- Register in Dashboard: Auth -> Hooks -> Custom Access Token -> this function.
--
-- RETURN FORMAT: Supabase requires the hook to return the ENTIRE event object
-- with the modified claims nested inside it. Returning only the new claims
-- (the old approach) caused a 500 on every auth call.
--
-- NEVER THROWS: every code path ends in a return, never a raise, so a bug
-- here can never take down login for all users.
create or replace function public.custom_jwt_claims(event jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    role_val text := 'operator';
    uid      uuid;
    claims   jsonb;
begin
    claims := event -> 'claims';

    -- Guard: malformed user_id -> return event unchanged (no crash)
    begin
        uid := (event ->> 'user_id')::uuid;
    exception when others then
        return jsonb_set(event, '{claims}', claims);
    end;

    -- The profile row may not exist yet at signup time (handle_new_user fires
    -- after the auth insert commits; the JWT hook may run first). SELECT INTO
    -- returns NULL rather than raising, so coalesce handles it cleanly.
    select app_role into role_val
      from public.profiles
     where id = uid;

    role_val := coalesce(role_val, 'operator');

    -- Reject unknown values: a bad DB row must not silently elevate privileges.
    -- 'worker' is admitted but is the lowest persona, so this never elevates.
    if role_val not in ('worker', 'operator', 'planner', 'engineer', 'admin') then
        role_val := 'operator';
    end if;

    -- Merge role into app_metadata inside the existing claims object.
    -- true = create the key if app_metadata is absent.
    claims := jsonb_set(claims, '{app_metadata,app_role}', to_jsonb(role_val), true);

    -- Return the full event with modified claims — Supabase auth requires this.
    return jsonb_set(event, '{claims}', claims);

exception when others then
    -- Last-resort catch-all: return event unchanged, never crash auth.
    return event;
end;
$$;

-- ----------------------------------------------------------- conversations
create table if not exists public.conversations (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid        not null references auth.users on delete cascade,
    title      text        not null default 'New conversation',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- the history list is always "mine, most recent first"
create index if not exists conversations_by_recency
    on public.conversations (user_id, updated_at desc);

alter table public.conversations enable row level security;

drop policy if exists "conversations are private to their owner"
    on public.conversations;
create policy "conversations are private to their owner"
    on public.conversations for all
    using  (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- --------------------------------------------------------------- messages
-- `answer` holds what the gateway returned alongside the text: citations,
-- mode, confidence, graph_version. Kept whole as jsonb so reopening a thread
-- shows the same evidence panel it showed live, and so a schema change on the
-- answer shape does not need a migration here.
create table if not exists public.messages (
    id              uuid primary key default gen_random_uuid(),
    conversation_id uuid        not null
                                references public.conversations on delete cascade,
    role            text        not null check (role in ('user', 'assistant')),
    text            text        not null default '',
    answer          jsonb,
    created_at      timestamptz not null default now()
);

create index if not exists messages_by_conversation
    on public.messages (conversation_id, created_at);

alter table public.messages enable row level security;

-- messages have no user_id of their own: ownership is the thread's ownership,
-- so the check goes through conversations
drop policy if exists "messages follow their conversation" on public.messages;
create policy "messages follow their conversation"
    on public.messages for all
    using (exists (select 1 from public.conversations c
                   where c.id = conversation_id and c.user_id = auth.uid()))
    with check (exists (select 1 from public.conversations c
                        where c.id = conversation_id and c.user_id = auth.uid()));

-- Sorting the history by updated_at only works if something maintains it.
create or replace function public.touch_conversation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    update public.conversations
       set updated_at = now()
     where id = new.conversation_id;
    return new;
end;
$$;

drop trigger if exists on_message_inserted on public.messages;
create trigger on_message_inserted
    after insert on public.messages
    for each row execute function public.touch_conversation();
