-- PlantMind control plane. Run once in the Supabase SQL editor
-- (Dashboard -> SQL Editor -> New query -> paste -> Run).
--
-- The knowledge graph lives in neo4j and is shared by the plant. Everything
-- here is per-person: who someone is, and what they have asked. That split is
-- why this is in supabase rather than behind the gateway - the gateway serves
-- the brain and stays stateless, and row-level security does the tenancy.

-- ---------------------------------------------------------------- profiles
-- Who the engineer is, in the terms a plant actually uses. The unit and
-- projects are not decoration: they are the context that decides which alerts
-- and which corner of the graph matter to this person.
create table if not exists public.profiles (
    id           uuid primary key references auth.users on delete cascade,
    full_name    text,
    employee_id  text,
    job_title    text,                        -- Reliability Engineer
    department   text,                        -- Maintenance
    plant        text,                        -- Haldia Refinery
    home_unit    text,                        -- Unit 200
    projects     text[]      not null default '{}',
    expertise    text[]      not null default '{}',
    updated_at   timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "profiles are private to their owner" on public.profiles;
create policy "profiles are private to their owner"
    on public.profiles for all
    using (auth.uid() = id)
    with check (auth.uid() = id);

-- A profile row must exist the moment someone signs up, or the app has to
-- special-case "signed in but no profile yet" everywhere.
--
-- The second step of the signup form rides along in raw_user_meta_data, which
-- is why this copies more than a name: an engineer who told us their unit on
-- the way in should never be asked again. security definer so it can write
-- past RLS during the signup transaction, when there is no session yet.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, full_name, job_title, department,
                                 plant, home_unit)
    values (new.id,
            coalesce(new.raw_user_meta_data ->> 'full_name',
                     split_part(new.email, '@', 1)),
            nullif(new.raw_user_meta_data ->> 'job_title', ''),
            nullif(new.raw_user_meta_data ->> 'department', ''),
            nullif(new.raw_user_meta_data ->> 'plant', ''),
            nullif(new.raw_user_meta_data ->> 'home_unit', ''))
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- Backfill anyone who signed up before this ran.
insert into public.profiles (id, full_name)
select u.id, split_part(u.email, '@', 1)
from auth.users u
on conflict (id) do nothing;

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
    using (auth.uid() = user_id)
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
