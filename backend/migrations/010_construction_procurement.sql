CREATE TABLE IF NOT EXISTS construction_suppliers (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 200),
 phone TEXT NOT NULL DEFAULT '',
 email TEXT NOT NULL DEFAULT '',
 website TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '',
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_suppliers_workspace ON construction_suppliers(workspace_id,name);
CREATE TABLE IF NOT EXISTS construction_purchases (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 supplier_id TEXT REFERENCES construction_suppliers(id) ON DELETE SET NULL,
 material_id TEXT NOT NULL REFERENCES construction_quantities(id) ON DELETE RESTRICT,
 receipt_file_id TEXT REFERENCES files(id) ON DELETE SET NULL,
 purchased_on TEXT NOT NULL CHECK(length(purchased_on)=10),
 quantity TEXT NOT NULL,
 unit_price_kopecks INTEGER NOT NULL CHECK(unit_price_kopecks>=0),
 status TEXT NOT NULL CHECK(status IN ('ordered','received')),
 notes TEXT NOT NULL DEFAULT '',
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_purchases_object ON construction_purchases(workspace_id,object_id,created_at DESC);
