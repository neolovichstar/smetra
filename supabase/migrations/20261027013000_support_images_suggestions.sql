BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';

CREATE TABLE IF NOT EXISTS smetra.support_images (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES smetra.chat_conversations(id) ON DELETE CASCADE,
  message_id TEXT NOT NULL REFERENCES smetra.chat_messages(id) ON DELETE CASCADE,
  uploader_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  mime TEXT NOT NULL CHECK(mime IN ('image/webp','image/jpeg')),
  content BYTEA NOT NULL CHECK(octet_length(content) BETWEEN 1 AND 700000),
  created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS support_images_message_idx ON smetra.support_images(message_id);
CREATE INDEX IF NOT EXISTS support_images_uploader_idx ON smetra.support_images(uploader_id);
CREATE INDEX IF NOT EXISTS support_images_conversation_idx ON smetra.support_images(conversation_id);

CREATE TABLE IF NOT EXISTS smetra.support_suggestions (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES smetra.chat_conversations(id) ON DELETE CASCADE,
  message_id TEXT NOT NULL UNIQUE REFERENCES smetra.chat_messages(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','reviewing','planned','done','declined')),
  created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS support_suggestions_state_idx ON smetra.support_suggestions(status,created_at DESC);

REVOKE ALL ON smetra.support_images,smetra.support_suggestions FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON smetra.support_images TO smetra_runtime;
GRANT SELECT,INSERT,UPDATE ON smetra.support_suggestions TO smetra_runtime;

-- The runtime role deliberately has no SELECT on chat_members/chat_messages.
-- Boolean-only SECURITY DEFINER checks preserve that denial while allowing
-- scoped RLS predicates. Locked search_path and revoked PUBLIC EXECUTE.
CREATE OR REPLACE FUNCTION smetra.runtime_support_member(p_conversation_id text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO ''
AS $
  SELECT EXISTS (
    SELECT 1 FROM smetra.chat_members m
    JOIN smetra.chat_conversations c ON c.id=m.conversation_id
    WHERE c.id=p_conversation_id AND c.kind='support'
      AND m.user_id=smetra.runtime_user_id()
  )
$;
CREATE OR REPLACE FUNCTION smetra.runtime_support_message_owned(
  p_conversation_id text, p_message_id text
)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO ''
AS $
  SELECT EXISTS (
    SELECT 1 FROM smetra.chat_messages msg
    JOIN smetra.chat_conversations c ON c.id=msg.conversation_id
    JOIN smetra.chat_members m ON m.conversation_id=c.id
    WHERE c.id=p_conversation_id AND c.kind='support'
      AND msg.id=p_message_id AND msg.sender_type='user'
      AND msg.sender_id=smetra.runtime_user_id()
      AND m.user_id=smetra.runtime_user_id()
  )
$;
REVOKE ALL ON FUNCTION smetra.runtime_support_member(text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION smetra.runtime_support_message_owned(text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION smetra.runtime_support_member(text) TO smetra_runtime;
GRANT EXECUTE ON FUNCTION smetra.runtime_support_message_owned(text,text) TO smetra_runtime;

ALTER TABLE smetra.support_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.support_images FORCE ROW LEVEL SECURITY;
CREATE POLICY support_images_read ON smetra.support_images FOR SELECT TO smetra_runtime
  USING (smetra.runtime_is_admin() OR smetra.runtime_support_member(conversation_id));
CREATE POLICY support_images_write ON smetra.support_images FOR INSERT TO smetra_runtime
  WITH CHECK (
    uploader_id=smetra.runtime_user_id()
    AND smetra.runtime_support_message_owned(conversation_id,message_id)
  );

ALTER TABLE smetra.support_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.support_suggestions FORCE ROW LEVEL SECURITY;
CREATE POLICY support_suggestions_admin_read ON smetra.support_suggestions FOR SELECT TO smetra_runtime
  USING (smetra.runtime_is_admin());
CREATE POLICY support_suggestions_user_insert ON smetra.support_suggestions FOR INSERT TO smetra_runtime
  WITH CHECK (user_id=smetra.runtime_user_id()
    AND smetra.runtime_support_message_owned(conversation_id,message_id));
CREATE POLICY support_suggestions_admin_update ON smetra.support_suggestions FOR UPDATE TO smetra_runtime
  USING (smetra.runtime_is_admin()) WITH CHECK (smetra.runtime_is_admin());
INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(67,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
