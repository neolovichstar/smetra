CREATE INDEX IF NOT EXISTS idx_catalog_recent
 ON catalog_items(workspace_id,last_used_at DESC);
