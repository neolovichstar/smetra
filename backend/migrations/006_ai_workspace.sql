CREATE TABLE IF NOT EXISTS assistant_conversations (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, context_entity TEXT NOT NULL DEFAULT '', context_id TEXT NOT NULL DEFAULT '',
 pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_conversations_user
 ON assistant_conversations(workspace_id,user_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS workspace_knowledge (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 title TEXT NOT NULL, content TEXT NOT NULL,
 kind TEXT NOT NULL DEFAULT 'reference' CHECK(kind IN ('reference','rule')),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspace_knowledge
 ON workspace_knowledge(workspace_id,enabled,updated_at DESC);
CREATE TABLE IF NOT EXISTS file_text_chunks (
 file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 page INTEGER NOT NULL CHECK(page>0), text TEXT NOT NULL,
 source_sha256 TEXT NOT NULL, PRIMARY KEY(file_id,page)
);
CREATE INDEX IF NOT EXISTS idx_file_text_chunks_workspace ON file_text_chunks(workspace_id,file_id);
