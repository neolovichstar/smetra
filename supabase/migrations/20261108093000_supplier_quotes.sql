-- Version 69: independently entered supplier quotes for landed-cost optimization.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
CREATE TABLE IF NOT EXISTS smetra.construction_supplier_quotes (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 material_id TEXT NOT NULL REFERENCES smetra.construction_quantities(id) ON DELETE CASCADE,
 supplier_name TEXT NOT NULL CHECK(length(supplier_name) BETWEEN 1 AND 200),
 unit_price_kopecks BIGINT NOT NULL CHECK(unit_price_kopecks>0),
 stock_quantity TEXT,
 min_order_quantity TEXT NOT NULL DEFAULT '0',
 delivery_kopecks BIGINT CHECK(delivery_kopecks>=0),
 delivery_days INTEGER CHECK(delivery_days BETWEEN 0 AND 3650),
 delivery_city TEXT NOT NULL DEFAULT '',
 expires_on TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '',
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_supplier_quotes_object ON smetra.construction_supplier_quotes(workspace_id,object_id,material_id);
ALTER TABLE smetra.construction_supplier_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.construction_supplier_quotes FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.construction_supplier_quotes FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.construction_supplier_quotes TO smetra_runtime;
CREATE POLICY supplier_quotes_workspace ON smetra.construction_supplier_quotes
 FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id));
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(69,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;