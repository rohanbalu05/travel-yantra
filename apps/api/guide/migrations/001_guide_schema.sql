-- Guide corpus: POIs, relations and the retrievable paragraphs.
-- Ported from travel-yantra-v1 migrations 001-004 and 006 (guide tables only),
-- folded into one idempotent file for plain Postgres with pgvector.

create extension if not exists vector;

create table if not exists poi (
  id bigint generated always as identity primary key,
  name text not null,
  name_kn text,
  city text not null,
  district text,
  lat double precision not null,
  lng double precision not null,
  category text not null check (category in ('temple','monument','museum','nature','viewpoint','market','food','experience')),
  tags text[] not null default '{}',
  typical_dwell_min int not null check (typical_dwell_min > 0),
  entry_fee_inr int not null default 0,
  opens time,
  closes time,
  closed_on int[] not null default '{}',  -- ISO weekday: 1=Mon .. 7=Sun
  best_time text,
  accessibility_notes text,
  elderly_friendly boolean not null default true,
  popularity int check (popularity between 1 and 5),
  source_url text,
  last_verified date,
  trust text not null default 'draft' check (trust in ('verified','draft','ai_generated')),
  unique (name, city)
);

create table if not exists poi_edge (
  from_poi bigint not null references poi(id) on delete cascade,
  to_poi bigint not null references poi(id) on delete cascade,
  relation text not null check (relation in ('same_dynasty','same_style','pairs_well_with','nearby')),
  weight real default 1.0,
  primary key (from_poi, to_poi, relation)
);

create table if not exists intercity_leg (
  id bigint generated always as identity primary key,
  from_city text not null,
  to_city text not null,
  mode text not null check (mode in ('car','bus','train')),
  distance_km int,
  duration_min int not null,
  is_estimated boolean not null default true,
  notes text,
  unique (from_city, to_city, mode)
);

create table if not exists advisory (
  id bigint generated always as identity primary key,
  poi_id bigint references poi(id) on delete cascade,
  city text,
  severity text not null check (severity in ('info','warning','closed')),
  message text not null unique,
  source text not null,
  valid_from date not null default current_date,
  valid_until date not null,
  created_by text not null default 'seed'
);

create table if not exists doc_chunk (
  id bigint generated always as identity primary key,
  poi_id bigint references poi(id) on delete set null,
  city text,
  title text,
  body text not null,
  chunk_type text not null check (chunk_type in ('hook','story','fact','sensory','taste','practical')),
  is_legend boolean not null default false,
  lang text not null default 'en',
  source_name text,
  source_url text,
  last_verified date,
  aliases text,
  retired boolean not null default false,
  theme text,
  tier int check (tier in (2, 5, 10)),
  body_tsv tsvector generated always as (
    to_tsvector('english', coalesce(title, '') || ' ' || body || ' ' || coalesce(aliases, ''))
  ) stored,
  embedding vector(384),
  constraint doc_chunk_city_title_key unique (city, title)
);
create index if not exists doc_chunk_body_tsv_idx on doc_chunk using gin (body_tsv);
create index if not exists doc_chunk_embedding_idx on doc_chunk using hnsw (embedding vector_cosine_ops);
create index if not exists doc_chunk_live_idx on doc_chunk (city) where not retired;
