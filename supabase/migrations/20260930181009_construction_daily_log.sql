BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE IF NOT EXISTS smetra.construction_daily_logs (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 zone_id TEXT REFERENCES smetra.construction_zones(id) ON DELETE SET NULL,
 quantity_id TEXT REFERENCES smetra.construction_quantities(id) ON DELETE SET NULL,
 fact_id TEXT REFERENCES smetra.construction_facts(id) ON DELETE SET NULL,
 work_date TEXT NOT NULL CHECK(length(work_date)=10),
 workers TEXT NOT NULL DEFAULT '' CHECK(length(workers)<=500),
 worker_count BIGINT NOT NULL DEFAULT 0 CHECK(worker_count BETWEEN 0 AND 100),
 work_description TEXT NOT NULL CHECK(length(work_description) BETWEEN 1 AND 2000),
 completed_quantity TEXT NOT NULL DEFAULT '0',
 unit TEXT NOT NULL DEFAULT '',
 comment TEXT NOT NULL DEFAULT '' CHECK(length(comment)<=2000),
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_construction_daily_logs_object
 ON smetra.construction_daily_logs(workspace_id,object_id,work_date DESC,created_at DESC);

CREATE TABLE IF NOT EXISTS smetra.construction_log_photos (
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 log_id TEXT NOT NULL REFERENCES smetra.construction_daily_logs(id) ON DELETE CASCADE,
 file_id TEXT NOT NULL REFERENCES smetra.files(id) ON DELETE CASCADE,
 created_at BIGINT NOT NULL,
 PRIMARY KEY(log_id,file_id)
);
CREATE INDEX IF NOT EXISTS idx_construction_log_photos_workspace
 ON smetra.construction_log_photos(workspace_id,object_id);

DO $$ DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['construction_daily_logs','construction_log_photos'] LOOP
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
 VALUES(12,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
