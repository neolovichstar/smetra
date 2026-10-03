CREATE TABLE IF NOT EXISTS quote_creation_requests (
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 actor_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 key_hash TEXT NOT NULL,
 request_hash TEXT NOT NULL,
 quote_id TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(workspace_id,actor_id,key_hash)
);
