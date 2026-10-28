-- One trip identity across revisions (P9): a revise updates the trip in place and counts the version.
ALTER TABLE trips ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
ALTER TABLE trips ADD COLUMN IF NOT EXISTS updated_at timestamptz;
