BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE IF NOT EXISTS smetra.construction_defects (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 zone_id TEXT REFERENCES smetra.construction_zones(id) ON DELETE SET NULL,
 photo_file_id TEXT REFERENCES smetra.files(id) ON DELETE SET NULL,
 description TEXT NOT NULL CHECK(length(description) BETWEEN 1 AND 2000),
 severity TEXT NOT NULL DEFAULT 'normal' CHECK(severity IN ('low','normal','high')),
 measurement_note TEXT NOT NULL DEFAULT '' CHECK(length(measurement_note)<=500),
 suggested_work TEXT NOT NULL DEFAULT '' CHECK(length(suggested_work)<=500),
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_progress','resolved')),
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_defects_object
 ON smetra.construction_defects(workspace_id,object_id,created_at DESC);
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.construction_defects TO smetra_runtime;
ALTER TABLE smetra.construction_defects ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.construction_defects FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.construction_defects FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id));
REVOKE ALL ON smetra.construction_defects FROM PUBLIC,anon,authenticated;

INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(11,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
