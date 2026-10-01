BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.catalog_items ADD COLUMN IF NOT EXISTS last_used_at BIGINT NOT NULL DEFAULT 0;
ALTER TABLE smetra.catalog_items ADD COLUMN IF NOT EXISTS usage_count BIGINT NOT NULL DEFAULT 0 CHECK(usage_count >= 0);
CREATE INDEX IF NOT EXISTS idx_catalog_recent ON smetra.catalog_items(workspace_id,last_used_at DESC);
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(19,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
