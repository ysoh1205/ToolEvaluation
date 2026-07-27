alter table public.tool_mapping_configs
add column if not exists status text;

update public.tool_mapping_configs
set status = case
  when jsonb_array_length(mappings) > 0
    and not exists (
      select 1
      from jsonb_array_elements(mappings) as mapping
      where jsonb_array_length(coalesce(mapping -> 'actions', '[]'::jsonb)) = 0
    )
    then 'completed'
  else 'draft'
end
where status is null;

alter table public.tool_mapping_configs
alter column status set default 'draft',
alter column status set not null;

alter table public.tool_mapping_configs
drop constraint if exists tool_mapping_configs_status_check;

alter table public.tool_mapping_configs
add constraint tool_mapping_configs_status_check
check (status in ('draft', 'completed'));

create index if not exists tool_mapping_configs_status_updated_at_idx
on public.tool_mapping_configs (status, updated_at desc);

