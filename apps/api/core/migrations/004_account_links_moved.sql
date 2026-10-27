-- Sign-in: whether a claimed browser's trips have moved to the account yet (retried until they have).
-- Links made before this column existed had their trips moved already, so they default to true.
ALTER TABLE account_links ADD COLUMN IF NOT EXISTS moved boolean NOT NULL DEFAULT true;
