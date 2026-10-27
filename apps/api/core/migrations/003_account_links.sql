-- Sign-in (HQ V3-AG): which anonymous browser ids have moved to which account. Idempotent.
CREATE TABLE IF NOT EXISTS account_links (
    anon_id   text PRIMARY KEY,
    uid       text NOT NULL,
    linked_at timestamptz NOT NULL DEFAULT now()
);
