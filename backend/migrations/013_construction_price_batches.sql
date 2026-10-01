CREATE TABLE IF NOT EXISTS construction_price_batches (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 created_by TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 undone_at INTEGER,
 before_json TEXT NOT NULL CHECK(length(before_json) <= 20000),
 after_hash TEXT NOT NULL CHECK(length(after_hash)=64)
);
CREATE INDEX IF NOT EXISTS idx_construction_price_batches_object
 ON construction_price_batches(workspace_id,object_id,created_at DESC);
