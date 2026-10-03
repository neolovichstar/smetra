CREATE TABLE IF NOT EXISTS smetra.creation_requests (
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('file','conversation')),
 key_hash TEXT NOT NULL, request_hash TEXT NOT NULL, record_id TEXT NOT NULL,
 created_at BIGINT NOT NULL,
 PRIMARY KEY(workspace_id,user_id,kind,key_hash)
);
ALTER TABLE smetra.creation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.creation_requests FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.creation_requests FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON smetra.creation_requests TO smetra_runtime;
CREATE POLICY smetra_runtime_scope ON smetra.creation_requests FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id) AND user_id=smetra.runtime_user_id())
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id) AND user_id=smetra.runtime_user_id());
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(22,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
