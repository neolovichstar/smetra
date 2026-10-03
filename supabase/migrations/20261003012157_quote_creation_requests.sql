BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.quote_creation_requests (
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 actor_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 key_hash TEXT NOT NULL,
 request_hash TEXT NOT NULL,
 quote_id TEXT NOT NULL,
 created_at BIGINT NOT NULL,
 PRIMARY KEY(workspace_id,actor_id,key_hash)
);
CREATE INDEX IF NOT EXISTS idx_quote_creation_requests_actor ON smetra.quote_creation_requests(actor_id);
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.quote_creation_requests TO smetra_runtime;
ALTER TABLE smetra.quote_creation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.quote_creation_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.quote_creation_requests FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id) AND actor_id=smetra.runtime_user_id())
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id) AND actor_id=smetra.runtime_user_id());
REVOKE ALL ON smetra.quote_creation_requests FROM PUBLIC,anon,authenticated;
-- The DDL event trigger retains automatic execution; API roles cannot invoke
-- its SECURITY DEFINER handler directly.
DO $$ BEGIN
 IF to_regprocedure('public.rls_auto_enable()') IS NOT NULL THEN
  REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM PUBLIC,anon,authenticated;
 END IF;
END $$;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(20,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
