BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.file_versions (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 file_id TEXT NOT NULL REFERENCES smetra.files(id) ON DELETE CASCADE,
 revision BIGINT NOT NULL,
 sha256 TEXT NOT NULL,
 content BYTEA NOT NULL,
 size BIGINT NOT NULL CHECK(size BETWEEN 1 AND 1100000),
 created_by TEXT NOT NULL,
 created_at BIGINT NOT NULL,
 UNIQUE(file_id,revision)
);
CREATE INDEX IF NOT EXISTS idx_file_versions_file ON smetra.file_versions(workspace_id,file_id,revision DESC);
GRANT SELECT,INSERT,DELETE ON smetra.file_versions TO smetra_runtime;
ALTER TABLE smetra.file_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.file_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.file_versions FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id));
REVOKE ALL ON smetra.file_versions FROM PUBLIC,anon,authenticated;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(16,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
