CREATE TABLE IF NOT EXISTS files (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 quote_id TEXT REFERENCES quotes(id) ON DELETE CASCADE,
 project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
 client_id TEXT REFERENCES clients(id) ON DELETE CASCADE,
 name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL CHECK(size>0),
 sha256 TEXT NOT NULL, storage_name TEXT NOT NULL UNIQUE,
 public INTEGER NOT NULL DEFAULT 0 CHECK(public IN (0,1)), created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_workspace ON files(workspace_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_quote ON files(quote_id,public);
CREATE TABLE IF NOT EXISTS ai_usage (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 action TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
 input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_user ON ai_usage(user_id,created_at DESC);
