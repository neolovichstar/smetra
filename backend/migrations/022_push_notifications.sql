CREATE TABLE IF NOT EXISTS push_devices (
 id TEXT PRIMARY KEY,
 installation_id TEXT NOT NULL UNIQUE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 session_token_hash TEXT NOT NULL DEFAULT '',
 token TEXT NOT NULL UNIQUE,
 platform TEXT NOT NULL DEFAULT 'android',
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 last_seen INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_push_devices_user ON push_devices(user_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS push_outbox (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 notification_id TEXT NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
 title TEXT NOT NULL,
 body TEXT NOT NULL,
 entity_id TEXT NOT NULL DEFAULT '',
 created_at INTEGER NOT NULL,
 next_attempt_at INTEGER NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0,
 lease_until INTEGER NOT NULL DEFAULT 0,
 sent_at INTEGER,
 last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_push_outbox_due ON push_outbox(sent_at,next_attempt_at,lease_until,created_at);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id,workspace_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace_status_due ON tasks(workspace_id,status,due_date);
CREATE INDEX IF NOT EXISTS idx_project_payments_workspace_created ON project_payments(workspace_id,created_at DESC);
INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(31,strftime('%s','now'));
