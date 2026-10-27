-- Generated Katha stories. The key covers the subject, length, language, the
-- pipeline version and the facts used, so new facts or a new pipeline miss.
create table if not exists katha_cache (
  key text primary key,
  story jsonb not null,
  notes jsonb,
  created_at timestamptz not null default now()
);
