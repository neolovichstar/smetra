CREATE TABLE IF NOT EXISTS catalog_price_history (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 item_id TEXT NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
 price INTEGER NOT NULL CHECK(price >= 0),
 cost_price INTEGER NOT NULL CHECK(cost_price >= 0),
 item_revision INTEGER NOT NULL,
 changed_by TEXT REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_catalog_price_history_item
 ON catalog_price_history(workspace_id,item_id,created_at DESC);
