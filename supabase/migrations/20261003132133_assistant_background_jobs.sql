CREATE TABLE IF NOT EXISTS smetra.assistant_jobs (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 conversation_id TEXT REFERENCES smetra.assistant_conversations(id) ON DELETE CASCADE,
 session_hash TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
 prompt TEXT NOT NULL, context TEXT NOT NULL DEFAULT 'null', quota_key TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','retry','completed','failed','cancelled')),
 progress TEXT NOT NULL DEFAULT 'В очереди', result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
 attempts BIGINT NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 cancel_requested BIGINT NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
 quota_refunded BIGINT NOT NULL DEFAULT 0 CHECK(quota_refunded IN (0,1)),
 lease_token TEXT NOT NULL DEFAULT '', lease_until BIGINT NOT NULL DEFAULT 0,
 next_attempt_at BIGINT NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
 UNIQUE(workspace_id,user_id,request_key)
);
CREATE INDEX IF NOT EXISTS idx_assistant_jobs_due ON smetra.assistant_jobs(status,next_attempt_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_assistant_jobs_actor ON smetra.assistant_jobs(workspace_id,user_id,created_at DESC);

ALTER TABLE smetra.assistant_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_jobs FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.assistant_jobs FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON smetra.assistant_jobs TO smetra_runtime;
GRANT UPDATE(status,progress,result,error,cancel_requested,quota_refunded,lease_token,lease_until,updated_at) ON smetra.assistant_jobs TO smetra_runtime;
CREATE POLICY smetra_runtime_scope ON smetra.assistant_jobs FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id) AND user_id=smetra.runtime_user_id())
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id) AND user_id=smetra.runtime_user_id());
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(21,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
