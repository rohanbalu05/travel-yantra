-- Cache for Google Places API (New) responses. Expiry is set by the client:
-- 1 day for searches, 7 days for place details.

create table if not exists places_cache (
  key text primary key,
  payload jsonb not null,
  fetched_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index if not exists places_cache_expires_idx on places_cache (expires_at);
