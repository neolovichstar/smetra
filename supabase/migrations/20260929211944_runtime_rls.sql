-- The API uses this NOLOGIN grant role through a separate, limited LOGIN role.
-- Context is set only with SET LOCAL inside the current request transaction.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='smetra_runtime') THEN
    CREATE ROLE smetra_runtime NOLOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA smetra TO smetra_runtime;

CREATE OR REPLACE FUNCTION smetra.runtime_user_id() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT s.user_id FROM smetra.sessions s
  JOIN smetra.users u ON u.id=s.user_id
  WHERE s.token_hash=nullif(current_setting('smetra.session_hash',true),'')
    AND s.expires_at>extract(epoch FROM now())::bigint
    AND u.blocked=0 AND u.deleted_at IS NULL
  LIMIT 1
$$;
REVOKE ALL ON FUNCTION smetra.runtime_user_id() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION smetra.runtime_user_id() TO smetra_runtime;

CREATE OR REPLACE FUNCTION smetra.runtime_workspace_allowed(target text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT EXISTS (
    SELECT 1 FROM smetra.workspace_members m
    WHERE m.workspace_id=target AND m.user_id=smetra.runtime_user_id()
  )
$$;
REVOKE ALL ON FUNCTION smetra.runtime_workspace_allowed(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION smetra.runtime_workspace_allowed(text) TO smetra_runtime;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'activity','catalog_items','clients','comments','custom_field_definitions',
    'documents','estimate_templates','expenses','files','intake_forms',
    'client_requests','leads','notifications','project_payments','project_stages',
    'projects','quotes','tasks'
  ] LOOP
    EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.%I TO smetra_runtime',table_name);
    EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY smetra_runtime_scope ON smetra.%I FOR ALL TO smetra_runtime '
      || 'USING (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') '
      || 'AND smetra.runtime_workspace_allowed(workspace_id)) '
      || 'WITH CHECK (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') '
      || 'AND smetra.runtime_workspace_allowed(workspace_id))',table_name
    );
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY['ai_usage','assistant_actions','assistant_messages'] LOOP
    EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.%I TO smetra_runtime',table_name);
    EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY smetra_runtime_scope ON smetra.%I FOR ALL TO smetra_runtime '
      || 'USING (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') '
      || 'AND smetra.runtime_workspace_allowed(workspace_id) AND user_id=smetra.runtime_user_id()) '
      || 'WITH CHECK (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') '
      || 'AND smetra.runtime_workspace_allowed(workspace_id) AND user_id=smetra.runtime_user_id())',table_name
    );
  END LOOP;
END $$;

GRANT SELECT,UPDATE ON smetra.workspaces TO smetra_runtime;
ALTER TABLE smetra.workspaces FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.workspaces FOR ALL TO smetra_runtime
  USING (smetra.runtime_workspace_allowed(id))
  WITH CHECK (smetra.runtime_workspace_allowed(id));

GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.workspace_members TO smetra_runtime;
ALTER TABLE smetra.workspace_members FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.workspace_members FOR ALL TO smetra_runtime
  USING (smetra.runtime_workspace_allowed(workspace_id))
  WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
              AND smetra.runtime_workspace_allowed(workspace_id));

GRANT SELECT(id,name,email,blocked,deleted_at,entitlement_until) ON smetra.users TO smetra_runtime;
ALTER TABLE smetra.users FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_read ON smetra.users FOR SELECT TO smetra_runtime
  USING (id=smetra.runtime_user_id() OR EXISTS (
    SELECT 1 FROM smetra.workspace_members m
    WHERE m.user_id=users.id
      AND m.workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
      AND smetra.runtime_workspace_allowed(m.workspace_id)
  ));

GRANT SELECT,INSERT ON smetra.events TO smetra_runtime;
ALTER TABLE smetra.events FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.events FOR ALL TO smetra_runtime
  USING (EXISTS (SELECT 1 FROM smetra.workspaces w
    WHERE w.id=nullif(current_setting('smetra.workspace_id',true),'')
      AND w.owner_id=events.user_id AND smetra.runtime_workspace_allowed(w.id)))
  WITH CHECK (EXISTS (SELECT 1 FROM smetra.workspaces w
    WHERE w.id=nullif(current_setting('smetra.workspace_id',true),'')
      AND w.owner_id=events.user_id AND smetra.runtime_workspace_allowed(w.id)));

GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.notification_reads TO smetra_runtime;
ALTER TABLE smetra.notification_reads FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.notification_reads FOR ALL TO smetra_runtime
  USING (user_id=smetra.runtime_user_id())
  WITH CHECK (user_id=smetra.runtime_user_id());

GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.quote_items,smetra.quote_versions TO smetra_runtime;
ALTER TABLE smetra.quote_items FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.quote_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.quote_items FOR ALL TO smetra_runtime
  USING (EXISTS (SELECT 1 FROM smetra.quotes q WHERE q.id=quote_id))
  WITH CHECK (EXISTS (SELECT 1 FROM smetra.quotes q WHERE q.id=quote_id));
CREATE POLICY smetra_runtime_scope ON smetra.quote_versions FOR ALL TO smetra_runtime
  USING (EXISTS (SELECT 1 FROM smetra.quotes q WHERE q.id=quote_id))
  WITH CHECK (EXISTS (SELECT 1 FROM smetra.quotes q WHERE q.id=quote_id));

GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.file_payloads TO smetra_runtime;
ALTER TABLE smetra.file_payloads FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.file_payloads FOR ALL TO smetra_runtime
  USING (EXISTS (SELECT 1 FROM smetra.files f WHERE f.id=file_id))
  WITH CHECK (EXISTS (SELECT 1 FROM smetra.files f WHERE f.id=file_id));

-- Only the current user's monthly assistant counter, never auth/IP throttles.
GRANT SELECT,INSERT,UPDATE ON smetra.rate_limits TO smetra_runtime;
ALTER TABLE smetra.rate_limits FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_assistant ON smetra.rate_limits FOR ALL TO smetra_runtime
  USING (key=encode(sha256(convert_to(
    'assistant:month:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),
    'UTF8')),'hex'))
  WITH CHECK (key=encode(sha256(convert_to(
    'assistant:month:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),
    'UTF8')),'hex'));

INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(7,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
