CREATE TABLE IF NOT EXISTS object_chat_threads (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 title TEXT NOT NULL, next_sequence INTEGER NOT NULL DEFAULT 0,
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL, created_at INTEGER NOT NULL,
 UNIQUE(workspace_id,object_id), UNIQUE(id,workspace_id)
);
CREATE TABLE IF NOT EXISTS object_chat_messages (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 thread_id TEXT NOT NULL, sequence INTEGER NOT NULL CHECK(sequence>0),
 sender_id TEXT REFERENCES users(id) ON DELETE SET NULL, sender_name TEXT NOT NULL,
 body TEXT NOT NULL, client_key TEXT NOT NULL, created_at INTEGER NOT NULL,
 FOREIGN KEY(thread_id,workspace_id) REFERENCES object_chat_threads(id,workspace_id) ON DELETE CASCADE,
 UNIQUE(thread_id,sequence), UNIQUE(thread_id,sender_id,client_key)
);
CREATE INDEX IF NOT EXISTS idx_object_chats_workspace ON object_chat_threads(workspace_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_object_messages_sender ON object_chat_messages(sender_id);
CREATE TABLE IF NOT EXISTS project_cash_risks (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 deficit_kopecks INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 1, updated_at INTEGER NOT NULL,
 UNIQUE(workspace_id,project_id)
);
