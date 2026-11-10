-- Resumable large PDF uploads. All parts remain private to their workspace.
CREATE TABLE IF NOT EXISTS file_upload_sessions (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name TEXT NOT NULL, bytes_expected INTEGER NOT NULL CHECK(bytes_expected BETWEEN 1 AND 100000000),
 sha256 TEXT NOT NULL, reference_type TEXT NOT NULL, reference_id TEXT NOT NULL DEFAULT '',
 public INTEGER NOT NULL DEFAULT 0 CHECK(public IN (0,1)),
 created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
 completed_file_id TEXT REFERENCES files(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_file_upload_session_owner ON file_upload_sessions(workspace_id,user_id,expires_at);
CREATE TABLE IF NOT EXISTS file_upload_parts (
 upload_id TEXT NOT NULL REFERENCES file_upload_sessions(id) ON DELETE CASCADE,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 part_number INTEGER NOT NULL CHECK(part_number BETWEEN 0 AND 99),
 sha256 TEXT NOT NULL, content BLOB NOT NULL,
 PRIMARY KEY(upload_id,part_number)
);
CREATE INDEX IF NOT EXISTS idx_file_upload_part_workspace ON file_upload_parts(workspace_id,upload_id);
