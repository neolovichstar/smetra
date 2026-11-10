BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.file_upload_sessions (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 name TEXT NOT NULL, bytes_expected BIGINT NOT NULL CHECK(bytes_expected BETWEEN 1 AND 100000000),
 sha256 TEXT NOT NULL, reference_type TEXT NOT NULL, reference_id TEXT NOT NULL DEFAULT '',
 public INTEGER NOT NULL DEFAULT 0 CHECK(public IN (0,1)),
 created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL,
 completed_file_id TEXT REFERENCES smetra.files(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_file_upload_session_owner ON smetra.file_upload_sessions(workspace_id,user_id,expires_at);
CREATE TABLE IF NOT EXISTS smetra.file_upload_parts (
 upload_id TEXT NOT NULL REFERENCES smetra.file_upload_sessions(id) ON DELETE CASCADE,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 part_number INTEGER NOT NULL CHECK(part_number BETWEEN 0 AND 99),
 sha256 TEXT NOT NULL, content BYTEA NOT NULL CHECK(octet_length(content) BETWEEN 1 AND 1000000),
 PRIMARY KEY(upload_id,part_number)
);
CREATE INDEX IF NOT EXISTS idx_file_upload_part_workspace ON smetra.file_upload_parts(workspace_id,upload_id);
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.file_upload_sessions, smetra.file_upload_parts TO smetra_runtime;
ALTER TABLE smetra.file_upload_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.file_upload_parts ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.file_upload_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.file_upload_parts FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.file_upload_sessions FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id));
CREATE POLICY smetra_runtime_scope ON smetra.file_upload_parts FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id));
REVOKE ALL ON smetra.file_upload_sessions,smetra.file_upload_parts FROM PUBLIC,anon,authenticated;
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(36,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
