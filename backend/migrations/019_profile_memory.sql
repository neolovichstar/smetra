CREATE TABLE IF NOT EXISTS user_profiles (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '',
 profession TEXT NOT NULL DEFAULT '', company TEXT NOT NULL DEFAULT '', about TEXT NOT NULL DEFAULT '',
 response_style TEXT NOT NULL DEFAULT 'concise' CHECK(response_style IN ('concise','balanced','detailed')),
 memory_enabled INTEGER NOT NULL DEFAULT 1 CHECK(memory_enabled IN (0,1)), updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS assistant_memory (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, title_key TEXT NOT NULL, content TEXT NOT NULL,
 source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual','assistant')),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
 UNIQUE(workspace_id,user_id,title_key)
);
CREATE INDEX IF NOT EXISTS idx_assistant_memory_user ON assistant_memory(user_id,workspace_id,updated_at DESC);
