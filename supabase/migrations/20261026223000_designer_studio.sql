BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE IF NOT EXISTS smetra.designer_projects (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 client_id TEXT REFERENCES smetra.clients(id) ON DELETE SET NULL,
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 200),
 description TEXT NOT NULL DEFAULT '',
 budget_kopecks BIGINT NOT NULL DEFAULT 0 CHECK(budget_kopecks>=0),
 revision BIGINT NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_designer_projects_workspace
 ON smetra.designer_projects(workspace_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.designer_rooms (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES smetra.designer_projects(id) ON DELETE CASCADE,
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
 notes TEXT NOT NULL DEFAULT '',
 revision BIGINT NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_designer_rooms_project
 ON smetra.designer_rooms(workspace_id,project_id,created_at);

CREATE TABLE IF NOT EXISTS smetra.designer_items (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES smetra.designer_projects(id) ON DELETE CASCADE,
 room_id TEXT REFERENCES smetra.designer_rooms(id) ON DELETE SET NULL,
 kind TEXT NOT NULL,
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 200),
 article TEXT NOT NULL DEFAULT '',
 supplier TEXT NOT NULL DEFAULT '',
 unit TEXT NOT NULL DEFAULT 'шт.',
 quantity TEXT NOT NULL DEFAULT '1',
 unit_price BIGINT NOT NULL DEFAULT 0 CHECK(unit_price>=0),
 notes TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'planned',
 revision BIGINT NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_designer_items_project
 ON smetra.designer_items(workspace_id,project_id,room_id,created_at);

DO $$
DECLARE table_name TEXT;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['designer_projects','designer_rooms','designer_items'] LOOP
    EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.%I TO smetra_runtime',table_name);
    EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY smetra_runtime_scope ON smetra.%I FOR ALL TO smetra_runtime '
      || 'USING (workspace_id=(SELECT nullif(current_setting(''smetra.workspace_id'',true),'''')) '
      || 'AND smetra.runtime_workspace_allowed(workspace_id)) '
      || 'WITH CHECK (workspace_id=(SELECT nullif(current_setting(''smetra.workspace_id'',true),'''')) '
      || 'AND smetra.runtime_workspace_allowed(workspace_id))',table_name
    );
    EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC,anon,authenticated',table_name);
  END LOOP;
END $$;

INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES (29,extract(epoch from now())::bigint)
 ON CONFLICT DO NOTHING;
COMMIT;
