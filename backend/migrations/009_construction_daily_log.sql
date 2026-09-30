CREATE TABLE IF NOT EXISTS construction_daily_logs (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 zone_id TEXT REFERENCES construction_zones(id) ON DELETE SET NULL,
 quantity_id TEXT REFERENCES construction_quantities(id) ON DELETE SET NULL,
 fact_id TEXT REFERENCES construction_facts(id) ON DELETE SET NULL,
 work_date TEXT NOT NULL CHECK(length(work_date)=10),
 workers TEXT NOT NULL DEFAULT '',
 worker_count INTEGER NOT NULL DEFAULT 0 CHECK(worker_count BETWEEN 0 AND 100),
 work_description TEXT NOT NULL CHECK(length(work_description) BETWEEN 1 AND 2000),
 completed_quantity TEXT NOT NULL DEFAULT '0',
 unit TEXT NOT NULL DEFAULT '',
 comment TEXT NOT NULL DEFAULT '' CHECK(length(comment)<=2000),
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_daily_logs_object
 ON construction_daily_logs(workspace_id,object_id,work_date DESC,created_at DESC);
CREATE TABLE IF NOT EXISTS construction_log_photos (
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 log_id TEXT NOT NULL REFERENCES construction_daily_logs(id) ON DELETE CASCADE,
 file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(log_id,file_id)
);
CREATE INDEX IF NOT EXISTS idx_construction_log_photos_workspace
 ON construction_log_photos(workspace_id,object_id);
