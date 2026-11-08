-- Supplier quotes are user-entered and scoped to one construction object/material.
CREATE TABLE IF NOT EXISTS construction_supplier_quotes (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES construction_objects(id) ON DELETE CASCADE,
 material_id TEXT NOT NULL REFERENCES construction_quantities(id) ON DELETE CASCADE,
 supplier_name TEXT NOT NULL CHECK(length(supplier_name) BETWEEN 1 AND 200),
 unit_price_kopecks INTEGER NOT NULL CHECK(unit_price_kopecks>0),
 stock_quantity TEXT,
 min_order_quantity TEXT NOT NULL DEFAULT '0',
 delivery_kopecks INTEGER CHECK(delivery_kopecks>=0),
 delivery_days INTEGER CHECK(delivery_days BETWEEN 0 AND 3650),
 delivery_city TEXT NOT NULL DEFAULT '',
 expires_on TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '',
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_supplier_quotes_object ON construction_supplier_quotes(workspace_id,object_id,material_id);