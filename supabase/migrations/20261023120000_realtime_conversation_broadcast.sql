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
  IF NEW.needs_human IS TRUE AND OLD.needs_human IS DISTINCT FROM TRUE THEN
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
INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(50,EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT(version) DO NOTHING;
COMMIT;
