CREATE TABLE IF NOT EXISTS file_versions (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 content BLOB NOT NULL,
 size INTEGER NOT NULL,
 created_by TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 UNIQUE(file_id,revision)
);
CREATE INDEX IF NOT EXISTS idx_file_versions_file ON file_versions(workspace_id,file_id,revision DESC);
