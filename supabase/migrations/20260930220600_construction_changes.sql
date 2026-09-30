BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.construction_changes (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 root_id TEXT NOT NULL,
 version BIGINT NOT NULL CHECK(version BETWEEN 1 AND 100),
 title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
 description TEXT NOT NULL DEFAULT '',
 items_json TEXT NOT NULL,
 amount_kopecks BIGINT NOT NULL CHECK(amount_kopecks>=0),
 deadline_days BIGINT NOT NULL DEFAULT 0 CHECK(deadline_days BETWEEN 0 AND 365),
 status TEXT NOT NULL CHECK(status IN ('draft','sent','approved','changes_requested','declined')),
 public_token TEXT UNIQUE,
 response_name TEXT NOT NULL DEFAULT '',
 response_comment TEXT NOT NULL DEFAULT '',
 sent_at BIGINT,
 decided_at BIGINT,
 expires_at BIGINT,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 UNIQUE(workspace_id,root_id,version)
);
CREATE INDEX IF NOT EXISTS idx_construction_changes_object ON smetra.construction_changes(workspace_id,object_id,created_at DESC);
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.construction_changes TO smetra_runtime;
ALTER TABLE smetra.construction_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.construction_changes FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.construction_changes FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id));
REVOKE ALL ON smetra.construction_changes FROM PUBLIC,anon,authenticated;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(14,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
