create table if not exists annotations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  document_id uuid references documents(id) on delete cascade,
  section_id uuid references document_sections(id) on delete cascade,
  type text not null check (type in ('question', 'note')),
  selected_text text not null,
  anchor jsonb,
  note text,
  thread jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists annotations_document_section_idx
on annotations(document_id, section_id);

create index if not exists annotations_user_id_idx
on annotations(user_id);
