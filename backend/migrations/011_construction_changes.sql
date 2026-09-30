CREATE TABLE IF NOT EXISTS construction_changes (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 root_id TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 100),
 title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
 description TEXT NOT NULL DEFAULT '',
 items_json TEXT NOT NULL,
 amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks>=0),
 deadline_days INTEGER NOT NULL DEFAULT 0 CHECK(deadline_days BETWEEN 0 AND 365),
 status TEXT NOT NULL CHECK(status IN ('draft','sent','approved','changes_requested','declined')),
 public_token TEXT UNIQUE,
 response_name TEXT NOT NULL DEFAULT '',
 response_comment TEXT NOT NULL DEFAULT '',
 sent_at INTEGER,
 decided_at INTEGER,
 expires_at INTEGER,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 UNIQUE(workspace_id,root_id,version)
);
CREATE INDEX IF NOT EXISTS idx_construction_changes_object ON construction_changes(workspace_id,object_id,created_at DESC);
