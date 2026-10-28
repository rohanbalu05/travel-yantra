-- On-demand Katha audio (HQ P7): text-to-speech characters spent per day, held under
-- KATHA_TTS_DAILY_CHARS across every API instance, and one row per story being read
-- aloud, so two requests never read the same chapter at once.
create table if not exists katha_tts_usage (
  day date primary key,
  chars integer not null default 0
);
create table if not exists katha_audio_job (
  audio_key text primary key,
  created_at timestamptz not null default now(),
  claimed_until timestamptz
);
