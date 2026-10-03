CREATE TABLE IF NOT EXISTS assistant_jobs (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 conversation_id TEXT REFERENCES assistant_conversations(id) ON DELETE CASCADE,
 session_hash TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
 prompt TEXT NOT NULL, context TEXT NOT NULL DEFAULT 'null', quota_key TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','retry','completed','failed','cancelled')),
 progress TEXT NOT NULL DEFAULT 'В очереди', result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
 quota_refunded INTEGER NOT NULL DEFAULT 0 CHECK(quota_refunded IN (0,1)),
 lease_token TEXT NOT NULL DEFAULT '', lease_until INTEGER NOT NULL DEFAULT 0,
 next_attempt_at INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
 UNIQUE(workspace_id,user_id,request_key)
);
CREATE INDEX IF NOT EXISTS idx_assistant_jobs_due ON assistant_jobs(status,next_attempt_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_assistant_jobs_actor ON assistant_jobs(workspace_id,user_id,created_at DESC);
