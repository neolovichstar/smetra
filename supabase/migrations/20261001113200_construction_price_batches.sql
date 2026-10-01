BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.construction_price_batches (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 created_by TEXT NOT NULL,
 created_at BIGINT NOT NULL,
 undone_at BIGINT,
 before_json TEXT NOT NULL CHECK(length(before_json) <= 20000),
 after_hash TEXT NOT NULL CHECK(length(after_hash)=64)
);
CREATE INDEX IF NOT EXISTS idx_construction_price_batches_object
 ON smetra.construction_price_batches(workspace_id,object_id,created_at DESC);
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.construction_price_batches TO smetra_runtime;
ALTER TABLE smetra.construction_price_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.construction_price_batches FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.construction_price_batches FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id));
REVOKE ALL ON smetra.construction_price_batches FROM PUBLIC,anon,authenticated;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(17,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
