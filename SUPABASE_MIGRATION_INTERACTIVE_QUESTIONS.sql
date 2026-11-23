alter table questions
add column if not exists section_id uuid references document_sections(id) on delete set null;

alter table questions
add column if not exists selected_text text;

alter table questions
add column if not exists anchor jsonb;

create index if not exists questions_document_section_idx
on questions(document_id, section_id);
