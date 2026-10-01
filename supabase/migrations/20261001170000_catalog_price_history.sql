BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.catalog_items ADD COLUMN IF NOT EXISTS favorite BIGINT NOT NULL DEFAULT 0 CHECK(favorite IN (0,1));
CREATE TABLE IF NOT EXISTS smetra.catalog_price_history (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 item_id TEXT NOT NULL REFERENCES smetra.catalog_items(id) ON DELETE CASCADE,
 price BIGINT NOT NULL CHECK(price >= 0),
 cost_price BIGINT NOT NULL CHECK(cost_price >= 0),
 item_revision BIGINT NOT NULL,
 changed_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_price_history_item
 ON smetra.catalog_price_history(workspace_id,item_id,created_at DESC);
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.catalog_price_history TO smetra_runtime;
ALTER TABLE smetra.catalog_price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.catalog_price_history FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.catalog_price_history FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id));
REVOKE ALL ON smetra.catalog_price_history FROM PUBLIC,anon,authenticated;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(18,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
