create extension if not exists pgcrypto;

create table if not exists public.tool_mapping_configs (
  id uuid primary key default gen_random_uuid(),
  schema_version integer not null default 1 check (schema_version > 0),
  server_name text not null unique check (char_length(server_name) between 1 and 100),
  tools_json jsonb not null,
  openapi_json jsonb not null,
  mappings jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.set_tool_mapping_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_tool_mapping_configs_updated_at
on public.tool_mapping_configs;

create trigger set_tool_mapping_configs_updated_at
before update on public.tool_mapping_configs
for each row execute function public.set_tool_mapping_updated_at();

alter table public.tool_mapping_configs enable row level security;

revoke all on table public.tool_mapping_configs from anon, authenticated;
grant all on table public.tool_mapping_configs to service_role;

