BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE IF NOT EXISTS smetra.construction_objects (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 client_id TEXT REFERENCES smetra.clients(id) ON DELETE SET NULL,
 quote_id TEXT REFERENCES smetra.quotes(id) ON DELETE SET NULL,
 project_id TEXT REFERENCES smetra.projects(id) ON DELETE SET NULL,
 name TEXT NOT NULL CHECK(length(name)<=200), description TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'survey', created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_objects_workspace
 ON smetra.construction_objects(workspace_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.construction_zones (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 parent_id TEXT REFERENCES smetra.construction_zones(id) ON DELETE SET NULL,
 name TEXT NOT NULL CHECK(length(name)<=120), kind TEXT NOT NULL DEFAULT 'room',
 length_m TEXT NOT NULL DEFAULT '0', width_m TEXT NOT NULL DEFAULT '0',
 height_m TEXT NOT NULL DEFAULT '0', openings_m2 TEXT NOT NULL DEFAULT '0',
 notes TEXT NOT NULL DEFAULT '', created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_zones_object
 ON smetra.construction_zones(workspace_id,object_id);

CREATE TABLE IF NOT EXISTS smetra.construction_measurements (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 zone_id TEXT REFERENCES smetra.construction_zones(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, symbol TEXT NOT NULL, value TEXT NOT NULL, unit TEXT NOT NULL,
 source TEXT NOT NULL DEFAULT 'manual', notes TEXT NOT NULL DEFAULT '',
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL, created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_measurements_object
 ON smetra.construction_measurements(workspace_id,object_id,zone_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_construction_measurements_symbol
 ON smetra.construction_measurements(object_id,symbol);

CREATE TABLE IF NOT EXISTS smetra.construction_quantities (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 zone_id TEXT REFERENCES smetra.construction_zones(id) ON DELETE SET NULL,
 parent_work_id TEXT REFERENCES smetra.construction_quantities(id) ON DELETE SET NULL,
 catalog_id TEXT REFERENCES smetra.catalog_items(id) ON DELETE SET NULL,
 kind TEXT NOT NULL, title TEXT NOT NULL CHECK(length(title)<=200), formula TEXT NOT NULL,
 quantity TEXT NOT NULL, unit TEXT NOT NULL,
 unit_price BIGINT NOT NULL DEFAULT 0 CHECK(unit_price>=0),
 cost_price BIGINT NOT NULL DEFAULT 0 CHECK(cost_price>=0),
 consumption_rate TEXT NOT NULL DEFAULT '0', waste_percent TEXT NOT NULL DEFAULT '0',
 coefficient TEXT NOT NULL DEFAULT '1', notes TEXT NOT NULL DEFAULT '',
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_quantities_object
 ON smetra.construction_quantities(workspace_id,object_id,zone_id);

CREATE TABLE IF NOT EXISTS smetra.construction_facts (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 quantity_id TEXT NOT NULL REFERENCES smetra.construction_quantities(id) ON DELETE CASCADE,
 quantity TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL, created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_facts_quantity
 ON smetra.construction_facts(workspace_id,quantity_id,created_at);

ALTER TABLE smetra.files ADD COLUMN IF NOT EXISTS construction_id TEXT
 REFERENCES smetra.construction_objects(id) ON DELETE CASCADE;
ALTER TABLE smetra.catalog_items ADD COLUMN IF NOT EXISTS item_type TEXT NOT NULL DEFAULT 'service';
ALTER TABLE smetra.catalog_items ADD COLUMN IF NOT EXISTS supplier TEXT NOT NULL DEFAULT '';
ALTER TABLE smetra.catalog_items ADD COLUMN IF NOT EXISTS article TEXT NOT NULL DEFAULT '';
ALTER TABLE smetra.catalog_items ADD COLUMN IF NOT EXISTS consumption_rate TEXT NOT NULL DEFAULT '0';
ALTER TABLE smetra.catalog_items ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT '';

DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'construction_objects','construction_zones','construction_measurements',
    'construction_quantities','construction_facts'
  ] LOOP
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
 VALUES(9,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
