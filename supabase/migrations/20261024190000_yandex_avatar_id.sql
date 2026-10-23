BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.users ADD COLUMN IF NOT EXISTS avatar_id TEXT NOT NULL DEFAULT '';
COMMIT;
