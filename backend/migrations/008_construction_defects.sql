CREATE TABLE IF NOT EXISTS construction_defects (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 zone_id TEXT REFERENCES construction_zones(id) ON DELETE SET NULL,
 photo_file_id TEXT REFERENCES files(id) ON DELETE SET NULL,
 description TEXT NOT NULL CHECK(length(description) BETWEEN 1 AND 2000),
 severity TEXT NOT NULL DEFAULT 'normal' CHECK(severity IN ('low','normal','high')),
 measurement_note TEXT NOT NULL DEFAULT '' CHECK(length(measurement_note)<=500),
 suggested_work TEXT NOT NULL DEFAULT '' CHECK(length(suggested_work)<=500),
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_progress','resolved')),
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_defects_object
 ON construction_defects(workspace_id,object_id,created_at DESC);
