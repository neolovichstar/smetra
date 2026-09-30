BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE IF NOT EXISTS smetra.construction_suppliers (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 200),
 phone TEXT NOT NULL DEFAULT '',
 email TEXT NOT NULL DEFAULT '',
 website TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '',
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_suppliers_workspace ON smetra.construction_suppliers(workspace_id,name);
CREATE TABLE IF NOT EXISTS smetra.construction_purchases (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 supplier_id TEXT REFERENCES smetra.construction_suppliers(id) ON DELETE SET NULL,
 material_id TEXT NOT NULL REFERENCES smetra.construction_quantities(id) ON DELETE RESTRICT,
 receipt_file_id TEXT REFERENCES smetra.files(id) ON DELETE SET NULL,
 purchased_on TEXT NOT NULL CHECK(length(purchased_on)=10),
 quantity TEXT NOT NULL,
 unit_price_kopecks BIGINT NOT NULL CHECK(unit_price_kopecks>=0),
 status TEXT NOT NULL CHECK(status IN ('ordered','received')),
 notes TEXT NOT NULL DEFAULT '',
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_purchases_object ON smetra.construction_purchases(workspace_id,object_id,created_at DESC);

DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['construction_suppliers','construction_purchases'] LOOP
    EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.%I TO smetra_runtime',table_name);
    EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY smetra_runtime_scope ON smetra.%I FOR ALL TO smetra_runtime '
      || 'USING (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') '
      || 'AND smetra.runtime_workspace_allowed(workspace_id)) '
      || 'WITH CHECK (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') '
      || 'AND smetra.runtime_workspace_allowed(workspace_id))',table_name
    );
    EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC,anon,authenticated',table_name);
  END LOOP;
END $$;

INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(13,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
