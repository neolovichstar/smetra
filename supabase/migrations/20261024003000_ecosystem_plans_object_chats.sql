BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.billing_intents ADD COLUMN IF NOT EXISTS bonus_ai_messages BIGINT NOT NULL DEFAULT 0;
ALTER TABLE smetra.push_outbox ADD COLUMN IF NOT EXISTS recipient_user_id TEXT REFERENCES smetra.users(id) ON DELETE CASCADE;
CREATE TABLE IF NOT EXISTS smetra.object_chat_threads (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 object_id TEXT NOT NULL REFERENCES smetra.construction_objects(id) ON DELETE CASCADE,
 title TEXT NOT NULL, next_sequence BIGINT NOT NULL DEFAULT 0,
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL, created_at BIGINT NOT NULL,
 UNIQUE(workspace_id,object_id), UNIQUE(id,workspace_id)
);
CREATE TABLE IF NOT EXISTS smetra.object_chat_messages (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 thread_id TEXT NOT NULL, sequence BIGINT NOT NULL CHECK(sequence>0),
 sender_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL, sender_name TEXT NOT NULL,
 body TEXT NOT NULL, client_key TEXT NOT NULL, created_at BIGINT NOT NULL,
 FOREIGN KEY(thread_id,workspace_id) REFERENCES smetra.object_chat_threads(id,workspace_id) ON DELETE CASCADE,
 UNIQUE(thread_id,sequence), UNIQUE(thread_id,sender_id,client_key)
);
CREATE INDEX IF NOT EXISTS idx_object_chats_workspace ON smetra.object_chat_threads(workspace_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_object_messages_sender ON smetra.object_chat_messages(sender_id);
CREATE TABLE IF NOT EXISTS smetra.project_cash_risks (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES smetra.projects(id) ON DELETE CASCADE,
 deficit_kopecks BIGINT NOT NULL DEFAULT 0, active BIGINT NOT NULL DEFAULT 0,
 revision BIGINT NOT NULL DEFAULT 1, updated_at BIGINT NOT NULL,
 UNIQUE(workspace_id,project_id)
);

DO $$
DECLARE t TEXT;
BEGIN
 FOREACH t IN ARRAY ARRAY['object_chat_threads','object_chat_messages','project_cash_risks'] LOOP
  EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC,anon,authenticated',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.%I TO smetra_runtime',t);
  EXECUTE format(
   'CREATE POLICY smetra_runtime_scope ON smetra.%I FOR ALL TO smetra_runtime USING (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') AND smetra.runtime_workspace_allowed(workspace_id)) WITH CHECK (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') AND smetra.runtime_workspace_allowed(workspace_id))',t);
 END LOOP;
END $$;
CREATE INDEX IF NOT EXISTS idx_push_outbox_recipient ON smetra.push_outbox(recipient_user_id) WHERE recipient_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_intents_workspace_payment ON smetra.billing_intents(workspace_id,payment_id);
CREATE OR REPLACE FUNCTION smetra.object_chat_realtime_allowed(topic TEXT)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT EXISTS(
  SELECT 1 FROM smetra.object_chat_threads t
  JOIN smetra.workspaces w ON w.id=t.workspace_id
  JOIN smetra.workspace_members m ON m.workspace_id=w.id
  JOIN smetra.sessions s ON s.user_id=m.user_id
  JOIN smetra.users u ON u.id=m.user_id
  WHERE topic='smetra:object:'||t.workspace_id||':'||t.id
   AND m.user_id=auth.jwt()->>'sub'
   AND s.token_hash=auth.jwt()->>'smetra_session'
   AND s.expires_at>EXTRACT(EPOCH FROM NOW())
   AND u.blocked=0 AND u.deleted_at IS NULL
   AND w.plan IN ('team','team_month','team_year','team_monthly','team_yearly')
   AND w.subscription_status IN ('active','trialing','paid')
   AND w.entitlement_until>EXTRACT(EPOCH FROM NOW())
 );
$$;
REVOKE ALL ON FUNCTION smetra.object_chat_realtime_allowed(TEXT) FROM PUBLIC,anon;
GRANT USAGE ON SCHEMA smetra TO authenticated;
GRANT EXECUTE ON FUNCTION smetra.object_chat_realtime_allowed(TEXT) TO authenticated;
CREATE POLICY smetra_object_chat_receive ON realtime.messages FOR SELECT TO authenticated
 USING (extension='broadcast' AND smetra.object_chat_realtime_allowed(realtime.topic()));
CREATE OR REPLACE FUNCTION smetra.broadcast_object_chat()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 BEGIN
  PERFORM realtime.send(jsonb_build_object('thread_id',NEW.thread_id,'sequence',NEW.sequence),
    'changed','smetra:object:'||NEW.workspace_id||':'||NEW.thread_id,TRUE);
 EXCEPTION WHEN OTHERS THEN
  RAISE WARNING 'Object chat broadcast deferred; durable history is available';
 END;
 RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION smetra.broadcast_object_chat() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER object_chat_broadcast AFTER INSERT ON smetra.object_chat_messages
 FOR EACH ROW EXECUTE FUNCTION smetra.broadcast_object_chat();
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(50,EXTRACT(EPOCH FROM NOW())::BIGINT) ON CONFLICT(version) DO NOTHING;
COMMIT;
