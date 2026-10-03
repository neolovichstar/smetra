-- Record IDs deliberately survive deletion of the created object: a retry must
-- report a removed result rather than silently recreate it.
CREATE TABLE IF NOT EXISTS creation_requests (
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('file','conversation')),
 key_hash TEXT NOT NULL, request_hash TEXT NOT NULL, record_id TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(workspace_id,user_id,kind,key_hash)
);
