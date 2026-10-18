BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- Restore the table used by file history on PostgreSQL deployments where it is absent.
CREATE TABLE IF NOT EXISTS smetra.file_versions (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 file_id TEXT NOT NULL REFERENCES smetra.files(id) ON DELETE CASCADE,
 revision BIGINT NOT NULL CHECK(revision > 0),
 sha256 TEXT NOT NULL,
 content BYTEA NOT NULL,
 size BIGINT NOT NULL CHECK(size > 0),
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 created_at BIGINT NOT NULL,
 UNIQUE(file_id,revision)
);
CREATE INDEX IF NOT EXISTS idx_file_versions_file_revision ON smetra.file_versions(workspace_id,file_id,revision DESC);
CREATE INDEX IF NOT EXISTS idx_file_versions_workspace_created ON smetra.file_versions(workspace_id,created_at DESC);
ALTER TABLE smetra.file_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.file_versions FORCE ROW LEVEL SECURITY;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.file_versions TO smetra_runtime;
REVOKE ALL ON smetra.file_versions FROM PUBLIC,anon,authenticated;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='smetra' AND tablename='file_versions' AND policyname='smetra_runtime_file_versions') THEN
    CREATE POLICY smetra_runtime_file_versions ON smetra.file_versions FOR ALL TO smetra_runtime
      USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))
      WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id));
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS smetra.push_devices (
 id TEXT PRIMARY KEY,
 installation_id TEXT NOT NULL UNIQUE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 session_token_hash TEXT NOT NULL DEFAULT '',
 token TEXT NOT NULL UNIQUE,
 platform TEXT NOT NULL DEFAULT 'android',
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 last_seen BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_push_devices_user ON smetra.push_devices(user_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.push_outbox (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 notification_id TEXT NOT NULL REFERENCES smetra.notifications(id) ON DELETE CASCADE,
 title TEXT NOT NULL,
 body TEXT NOT NULL,
 entity_id TEXT NOT NULL DEFAULT '',
 created_at BIGINT NOT NULL,
 next_attempt_at BIGINT NOT NULL,
 attempts BIGINT NOT NULL DEFAULT 0,
 lease_until BIGINT NOT NULL DEFAULT 0,
 sent_at BIGINT,
 last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_push_outbox_due ON smetra.push_outbox(sent_at,next_attempt_at,lease_until,created_at);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON smetra.workspace_members(user_id,workspace_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace_status_due ON smetra.tasks(workspace_id,status,due_date);
CREATE INDEX IF NOT EXISTS idx_project_payments_workspace_created ON smetra.project_payments(workspace_id,created_at DESC);

ALTER TABLE smetra.push_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.push_devices FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.push_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.push_outbox FORCE ROW LEVEL SECURITY;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.push_devices TO smetra_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.push_outbox TO smetra_runtime;
REVOKE ALL ON smetra.push_devices,smetra.push_outbox FROM PUBLIC,anon,authenticated;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='smetra' AND tablename='push_devices' AND policyname='smetra_runtime_push_devices') THEN
    CREATE POLICY smetra_runtime_push_devices ON smetra.push_devices FOR ALL TO smetra_runtime
      USING (user_id=smetra.runtime_user_id()) WITH CHECK (user_id=smetra.runtime_user_id());
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='smetra' AND tablename='push_outbox' AND policyname='smetra_runtime_push_outbox') THEN
    CREATE POLICY smetra_runtime_push_outbox ON smetra.push_outbox FOR ALL TO smetra_runtime
      USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))
      WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id));
  END IF;
END $$;

INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(30,extract(epoch FROM now())::BIGINT) ON CONFLICT DO NOTHING;
COMMIT;
