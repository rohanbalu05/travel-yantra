-- Trips (card #37). Idempotent: applied by core.trips.PgStore on first connect.
CREATE TABLE IF NOT EXISTS trips (
    id          text PRIMARY KEY,
    share_token text NOT NULL UNIQUE,
    owner       text,
    revised_from text REFERENCES trips (id),
    itinerary   jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS trips_owner_idx ON trips (owner);
