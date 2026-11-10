-- Version 74: version text extraction independently of the established method enum.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='20s';
ALTER TABLE smetra.files ADD COLUMN IF NOT EXISTS index_version integer NOT NULL DEFAULT 1
 CHECK(index_version>=1);
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(74,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
