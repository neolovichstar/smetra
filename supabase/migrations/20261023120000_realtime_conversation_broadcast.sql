-- Supabase Realtime Broadcast invalidation for in-app chat.
-- Broadcast only opaque event signals; chat bodies stay behind the membership-checked API.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.conversations ADD COLUMN IF NOT EXISTS realtime_topic TEXT;
UPDATE smetra.conversations SET realtime_topic=gen_random_uuid()::text || gen_random_uuid()::text
WHERE realtime_topic IS NULL OR realtime_topic='';
ALTER TABLE smetra.conversations
  ALTER COLUMN realtime_topic SET DEFAULT (gen_random_uuid()::text || gen_random_uuid()::text),
  ALTER COLUMN realtime_topic SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_realtime_topic ON smetra.conversations(realtime_topic);
ALTER TABLE smetra.user_directory ADD COLUMN IF NOT EXISTS inbox_topic TEXT;
UPDATE smetra.user_directory SET inbox_topic=gen_random_uuid()::text || gen_random_uuid()::text
WHERE inbox_topic IS NULL OR inbox_topic='';
ALTER TABLE smetra.user_directory
  ALTER COLUMN inbox_topic SET DEFAULT (gen_random_uuid()::text || gen_random_uuid()::text),
  ALTER COLUMN inbox_topic SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_directory_inbox_topic ON smetra.user_directory(inbox_topic);

ALTER TABLE smetra.workspaces ADD COLUMN IF NOT EXISTS realtime_topic TEXT;
UPDATE smetra.workspaces SET realtime_topic=gen_random_uuid()::text || gen_random_uuid()::text
WHERE realtime_topic IS NULL OR realtime_topic='';
ALTER TABLE smetra.workspaces
  ALTER COLUMN realtime_topic SET DEFAULT (gen_random_uuid()::text || gen_random_uuid()::text),
  ALTER COLUMN realtime_topic SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_realtime_topic ON smetra.workspaces(realtime_topic);

-- Coalesce invalidation broadcasts to one event per workspace per transaction.
CREATE TABLE IF NOT EXISTS smetra.workspace_change_outbox (
  transaction_id BIGINT NOT NULL,
  workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
  created_at BIGINT NOT NULL,
  PRIMARY KEY(transaction_id,workspace_id)
);
ALTER TABLE smetra.workspace_change_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.workspace_change_outbox FORCE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_workspace_change_outbox_created
  ON smetra.workspace_change_outbox(created_at);

CREATE OR REPLACE FUNCTION smetra.broadcast_workspace_invalidation()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $workspace_invalidation$
DECLARE
  v_workspace_id TEXT;
  v_topic TEXT;
  v_inserted INTEGER;
BEGIN
  IF TG_OP='DELETE' THEN v_workspace_id := OLD.workspace_id;
  ELSE v_workspace_id := NEW.workspace_id;
  END IF;
  IF v_workspace_id IS NULL THEN RETURN NULL; END IF;
  SELECT w.realtime_topic INTO v_topic FROM smetra.workspaces w WHERE w.id=v_workspace_id;
  IF v_topic IS NULL OR v_topic='' THEN RETURN NULL; END IF;
  INSERT INTO smetra.workspace_change_outbox(transaction_id,workspace_id,created_at)
  VALUES(txid_current(),v_workspace_id,EXTRACT(EPOCH FROM NOW())::BIGINT)
  ON CONFLICT(transaction_id,workspace_id) DO NOTHING;
  GET DIAGNOSTICS v_inserted = ROW_COUNT;
  IF v_inserted=1 THEN
    PERFORM realtime.send(jsonb_build_object('v',1),'workspace_changed',v_topic,FALSE);
  END IF;
  -- Bounded opportunistic cleanup; this table stores no document or user content.
  IF mod(txid_current(),1000)=0 THEN
    DELETE FROM smetra.workspace_change_outbox
    WHERE created_at < EXTRACT(EPOCH FROM NOW())::BIGINT - 86400;
  END IF;
  RETURN NULL;
END;
$workspace_invalidation$;
REVOKE ALL ON FUNCTION smetra.broadcast_workspace_invalidation() FROM PUBLIC;

DO $workspace_triggers$
DECLARE
  v_table TEXT;
  v_tables TEXT[] := ARRAY[
    'workspace_members','quotes','quote_items','quote_versions','clients','catalog_items',
    'projects','project_stages','tasks','leads','project_payments','expenses','comments',
    'notifications','custom_field_definitions','estimate_templates','documents','files',
    'intake_forms','client_requests','assistant_messages','assistant_actions','ai_usage',
    'construction_objects','construction_zones','construction_measurements','construction_quantities',
    'construction_facts','construction_defects','construction_daily_logs','construction_log_photos',
    'construction_suppliers','construction_purchases','construction_changes','construction_price_batches',
    'catalog_price_history','workspace_knowledge','file_text_chunks','file_versions'
  ];
BEGIN
  FOREACH v_table IN ARRAY v_tables LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='smetra'
               AND table_name=v_table AND column_name='workspace_id') THEN
      EXECUTE format('DROP TRIGGER IF EXISTS workspace_broadcast_invalidation ON smetra.%I',v_table);
      EXECUTE format('CREATE TRIGGER workspace_broadcast_invalidation AFTER INSERT OR UPDATE OR DELETE ON smetra.%I FOR EACH ROW EXECUTE FUNCTION smetra.broadcast_workspace_invalidation()',
                     v_table);
    END IF;
  END LOOP;
END;
$workspace_triggers$;

CREATE OR REPLACE FUNCTION smetra.broadcast_message_invalidation()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $realtime_message$
DECLARE v_topic TEXT;
BEGIN
  SELECT c.realtime_topic INTO v_topic FROM smetra.conversations c WHERE c.id=NEW.conversation_id;
  IF v_topic IS NOT NULL AND v_topic<>'' THEN
    PERFORM realtime.send(jsonb_build_object('v',1),'message_changed',v_topic,FALSE);
  END IF;
  PERFORM realtime.send(jsonb_build_object('v',1),'inbox_changed',d.inbox_topic,FALSE)
  FROM smetra.conversation_members cm JOIN smetra.user_directory d ON d.user_id=cm.user_id
  WHERE cm.conversation_id=NEW.conversation_id AND d.inbox_topic IS NOT NULL AND d.inbox_topic<>'';
  RETURN NEW;
END;
$realtime_message$;
REVOKE ALL ON FUNCTION smetra.broadcast_message_invalidation() FROM PUBLIC;
DROP TRIGGER IF EXISTS messages_broadcast_invalidation ON smetra.messages;
CREATE TRIGGER messages_broadcast_invalidation AFTER INSERT ON smetra.messages
FOR EACH ROW EXECUTE FUNCTION smetra.broadcast_message_invalidation();
CREATE OR REPLACE FUNCTION smetra.broadcast_membership_invalidation()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $realtime_member$
DECLARE v_topic TEXT;
BEGIN
  SELECT d.inbox_topic INTO v_topic FROM smetra.user_directory d WHERE d.user_id=NEW.user_id;
  IF v_topic IS NOT NULL AND v_topic<>'' THEN
    PERFORM realtime.send(jsonb_build_object('v',1),'inbox_changed',v_topic,FALSE);
  END IF;
  RETURN NEW;
END;
$realtime_member$;
REVOKE ALL ON FUNCTION smetra.broadcast_membership_invalidation() FROM PUBLIC;
DROP TRIGGER IF EXISTS conversation_members_broadcast_invalidation ON smetra.conversation_members;
CREATE TRIGGER conversation_members_broadcast_invalidation AFTER INSERT ON smetra.conversation_members
FOR EACH ROW EXECUTE FUNCTION smetra.broadcast_membership_invalidation();
CREATE OR REPLACE FUNCTION smetra.broadcast_support_escalation()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $realtime_support$
DECLARE v_topic TEXT;
BEGIN
  IF NEW.needs_human=1 AND OLD.needs_human IS DISTINCT FROM 1 THEN
    FOR v_topic IN
      SELECT d.inbox_topic FROM smetra.users u JOIN smetra.user_directory d ON d.user_id=u.id
      WHERE u.role='admin' AND u.blocked=0 AND u.deleted_at IS NULL
        AND d.inbox_topic IS NOT NULL AND d.inbox_topic<>''
    LOOP
      PERFORM realtime.send(jsonb_build_object('v',1),'support_escalated',v_topic,FALSE);
    END LOOP;
  END IF;
  RETURN NEW;
END;
$realtime_support$;
REVOKE ALL ON FUNCTION smetra.broadcast_support_escalation() FROM PUBLIC;
DROP TRIGGER IF EXISTS support_broadcast_escalation ON smetra.support;
CREATE TRIGGER support_broadcast_escalation AFTER UPDATE OF needs_human ON smetra.support
FOR EACH ROW EXECUTE FUNCTION smetra.broadcast_support_escalation();
COMMENT ON COLUMN smetra.conversations.realtime_topic IS 'Random capability for invalidation-only broadcasts; never contains chat content.';
COMMENT ON COLUMN smetra.user_directory.inbox_topic IS 'Per-user random capability for inbox invalidation signals only.';
COMMENT ON COLUMN smetra.workspaces.realtime_topic IS 'Random workspace capability for data-free change invalidations; records remain behind backend authorization.';
INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(50,EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT(version) DO NOTHING;
COMMIT;
