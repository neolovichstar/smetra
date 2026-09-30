CREATE TABLE IF NOT EXISTS construction_objects (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 client_id TEXT REFERENCES clients(id) ON DELETE SET NULL,
 quote_id TEXT REFERENCES quotes(id) ON DELETE SET NULL,
 project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
 name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'survey',
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_objects_workspace ON construction_objects(workspace_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS construction_zones (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 parent_id TEXT REFERENCES construction_zones(id) ON DELETE SET NULL,
 name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'room',
 length_m TEXT NOT NULL DEFAULT '0', width_m TEXT NOT NULL DEFAULT '0',
 height_m TEXT NOT NULL DEFAULT '0', openings_m2 TEXT NOT NULL DEFAULT '0',
 notes TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_zones_object ON construction_zones(workspace_id,object_id);
CREATE TABLE IF NOT EXISTS construction_measurements (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 zone_id TEXT REFERENCES construction_zones(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, symbol TEXT NOT NULL, value TEXT NOT NULL, unit TEXT NOT NULL,
 source TEXT NOT NULL DEFAULT 'manual', notes TEXT NOT NULL DEFAULT '',
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_measurements_object ON construction_measurements(workspace_id,object_id,zone_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_construction_measurements_symbol ON construction_measurements(object_id,symbol);
CREATE TABLE IF NOT EXISTS construction_quantities (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 zone_id TEXT REFERENCES construction_zones(id) ON DELETE SET NULL,
 parent_work_id TEXT REFERENCES construction_quantities(id) ON DELETE SET NULL,
 catalog_id TEXT REFERENCES catalog_items(id) ON DELETE SET NULL,
 kind TEXT NOT NULL, title TEXT NOT NULL, formula TEXT NOT NULL,
 quantity TEXT NOT NULL, unit TEXT NOT NULL,
 unit_price INTEGER NOT NULL DEFAULT 0 CHECK(unit_price>=0),
 cost_price INTEGER NOT NULL DEFAULT 0 CHECK(cost_price>=0),
 consumption_rate TEXT NOT NULL DEFAULT '0', waste_percent TEXT NOT NULL DEFAULT '0',
 coefficient TEXT NOT NULL DEFAULT '1', notes TEXT NOT NULL DEFAULT '',
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_quantities_object ON construction_quantities(workspace_id,object_id,zone_id);
CREATE TABLE IF NOT EXISTS construction_facts (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 quantity_id TEXT NOT NULL REFERENCES construction_quantities(id) ON DELETE CASCADE,
 quantity TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_facts_quantity ON construction_facts(workspace_id,quantity_id,created_at);
