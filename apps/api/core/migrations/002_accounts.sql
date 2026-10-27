-- Accounts (HQ V3-AB): consents and ratings keyed by an anonymous per-browser id. Idempotent.
CREATE TABLE IF NOT EXISTS consents (
    uid          text PRIMARY KEY,
    plan_history boolean NOT NULL DEFAULT false,
    location     boolean NOT NULL DEFAULT false,
    analytics    boolean NOT NULL DEFAULT false,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ratings (
    id         bigserial PRIMARY KEY,
    uid        text,
    plan_id    text,
    score      smallint NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment    text,
    lang       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ratings_uid_idx ON ratings (uid);
