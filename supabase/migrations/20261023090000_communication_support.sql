-- Public user IDs, one-to-one and workspace conversations, support AI and escalation.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

ALTER TABLE smetra.users ADD COLUMN IF NOT EXISTS public_id TEXT NOT NULL DEFAULT '';
UPDATE smetra.users
SET public_id='SM-' || upper(substr(replace(id,'-',''),1,16))
WHERE public_id='';
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_public_id ON smetra.users(public_id);

CREATE TABLE IF NOT EXISTS smetra.user_directory (
  public_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE REFERENCES smetra.users(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  profession TEXT NOT NULL DEFAULT '',
  company TEXT NOT NULL DEFAULT '',
  visible BOOLEAN NOT NULL DEFAULT TRUE,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL DEFAULT 0
);
CREATE OR REPLACE FUNCTION smetra.assign_public_user_id()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = smetra, pg_temp
AS $public_id$
BEGIN
  IF NEW.public_id IS NULL OR NEW.public_id = '' THEN
    NEW.public_id := 'SM-' || upper(substr(replace(NEW.id,'-',''),1,16));
  END IF;
  RETURN NEW;
END
$public_id$;
DROP TRIGGER IF EXISTS users_assign_public_id ON smetra.users;
CREATE TRIGGER users_assign_public_id
BEFORE INSERT ON smetra.users
FOR EACH ROW EXECUTE FUNCTION smetra.assign_public_user_id();

CREATE OR REPLACE FUNCTION smetra.seed_user_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = smetra, pg_temp
AS $directory$
BEGIN
  INSERT INTO smetra.user_directory(public_id,user_id,display_name,profession,company,visible,created_at,updated_at)
  VALUES(NEW.public_id,NEW.id,NEW.name,'','',TRUE,NEW.created_at,0)
  ON CONFLICT(user_id) DO UPDATE SET public_id=excluded.public_id,display_name=excluded.display_name;
  RETURN NEW;
END
$directory$;
DROP TRIGGER IF EXISTS users_seed_directory ON smetra.users;
REVOKE ALL ON FUNCTION smetra.assign_public_user_id() FROM PUBLIC;
DROP TRIGGER IF EXISTS users_seed_directory ON smetra.users;
CREATE TRIGGER users_seed_directory
AFTER INSERT ON smetra.users
FOR EACH ROW EXECUTE FUNCTION smetra.seed_user_directory();
REVOKE ALL ON FUNCTION smetra.seed_user_directory() FROM PUBLIC;

CREATE OR REPLACE FUNCTION smetra.sync_user_directory_profile()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = smetra, pg_temp
AS $directory_profile$
DECLARE
  v_public_id TEXT;
  v_name TEXT;
  v_created_at BIGINT;
  v_display_name TEXT;
BEGIN
  SELECT public_id,name,created_at INTO v_public_id,v_name,v_created_at
  FROM smetra.users WHERE id=NEW.user_id;
  v_display_name := coalesce(nullif(btrim(concat_ws(' ',NEW.first_name,NEW.last_name)),''),v_name);
  INSERT INTO smetra.user_directory(public_id,user_id,display_name,profession,company,visible,created_at,updated_at)
  VALUES(v_public_id,NEW.user_id,v_display_name,coalesce(NEW.profession,''),coalesce(NEW.company,''),TRUE,v_created_at,coalesce(NEW.updated_at,0))
  ON CONFLICT(user_id) DO UPDATE SET
    public_id=excluded.public_id,display_name=excluded.display_name,
    profession=excluded.profession,company=excluded.company,updated_at=excluded.updated_at;
  RETURN NEW;
END
$directory_profile$;
REVOKE ALL ON FUNCTION smetra.sync_user_directory_profile() FROM PUBLIC;
DROP TRIGGER IF EXISTS user_profiles_sync_directory ON smetra.user_profiles;
CREATE TRIGGER user_profiles_sync_directory
AFTER INSERT OR UPDATE OF first_name,last_name,profession,company,updated_at ON smetra.user_profiles
FOR EACH ROW EXECUTE FUNCTION smetra.sync_user_directory_profile();

INSERT INTO smetra.user_directory(public_id,user_id,display_name,profession,company,visible,created_at,updated_at)
SELECT u.public_id,u.id,u.name,coalesce(p.profession,''),coalesce(p.company,''),TRUE,u.created_at,coalesce(p.updated_at,0)
FROM smetra.users u LEFT JOIN smetra.user_profiles p ON p.user_id=u.id
ON CONFLICT(user_id) DO NOTHING;
CREATE INDEX IF NOT EXISTS idx_user_directory_name ON smetra.user_directory(lower(display_name));
CREATE INDEX IF NOT EXISTS idx_user_directory_profession ON smetra.user_directory(lower(profession));

ALTER TABLE smetra.support ADD COLUMN IF NOT EXISTS subject TEXT NOT NULL DEFAULT 'Вопрос в поддержку';
ALTER TABLE smetra.support ADD COLUMN IF NOT EXISTS needs_human BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE smetra.support ADD COLUMN IF NOT EXISTS conversation_id TEXT;
ALTER TABLE smetra.support ADD COLUMN IF NOT EXISTS updated_at BIGINT NOT NULL DEFAULT 0;
ALTER TABLE smetra.support ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'normal';
ALTER TABLE smetra.support ADD COLUMN IF NOT EXISTS ai_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE smetra.support ADD COLUMN IF NOT EXISTS assigned_admin_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL;
UPDATE smetra.support SET updated_at=created_at WHERE updated_at=0;
DO $support_checks$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='support_priority_check') THEN
    ALTER TABLE smetra.support ADD CONSTRAINT support_priority_check
      CHECK(priority IN ('low','normal','high','urgent'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='support_ai_state_check') THEN
    ALTER TABLE smetra.support ADD CONSTRAINT support_ai_state_check
      CHECK(ai_state IN ('active','human','resolved'));
  END IF;
END
$support_checks$;

CREATE TABLE IF NOT EXISTS smetra.conversations (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('direct','quote','workspace','community','support')),
  title TEXT NOT NULL DEFAULT '',
  workspace_id TEXT REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
  quote_id TEXT REFERENCES smetra.quotes(id) ON DELETE CASCADE,
  object_id TEXT REFERENCES smetra.projects(id) ON DELETE CASCADE,
  category TEXT NOT NULL DEFAULT '',
  created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','closed','archived')),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_quote ON smetra.conversations(quote_id)
  WHERE kind='quote' AND quote_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_workspace_object ON smetra.conversations(workspace_id,(coalesce(object_id,'')))
  WHERE kind='workspace' AND workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON smetra.conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON smetra.conversations(workspace_id,kind,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.conversation_members (
  conversation_id TEXT NOT NULL REFERENCES smetra.conversations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('owner','member','customer','admin','participant')),
  joined_at BIGINT NOT NULL,
  last_read_at BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY(conversation_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_conversation_members_user ON smetra.conversation_members(user_id,joined_at DESC);

CREATE TABLE IF NOT EXISTS smetra.direct_chat_pairs (
  user_low TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  user_high TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL UNIQUE REFERENCES smetra.conversations(id) ON DELETE CASCADE,
  created_at BIGINT NOT NULL,
  PRIMARY KEY(user_low,user_high),
  CHECK(user_low < user_high)
);
CREATE INDEX IF NOT EXISTS idx_direct_chat_pairs_high ON smetra.direct_chat_pairs(user_high,user_low);

CREATE TABLE IF NOT EXISTS smetra.messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES smetra.conversations(id) ON DELETE CASCADE,
  sender_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
  sender_role TEXT NOT NULL CHECK(sender_role IN ('user','admin','ai','system')),
  body TEXT NOT NULL CHECK(char_length(body) BETWEEN 1 AND 4000),
  payload TEXT NOT NULL DEFAULT '{}',
  created_at BIGINT NOT NULL,
  edited_at BIGINT,
  deleted_at BIGINT
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON smetra.messages(conversation_id,created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS idx_messages_sender_created ON smetra.messages(sender_id,created_at DESC) WHERE sender_id IS NOT NULL;

UPDATE smetra.support
SET conversation_id='support-' || id
WHERE conversation_id IS NULL;
INSERT INTO smetra.conversations(id,kind,title,created_by,status,created_at,updated_at)
SELECT 'support-' || s.id,'support',coalesce(nullif(s.subject,''),'Вопрос в поддержку'),s.user_id,
       CASE WHEN s.status='closed' THEN 'closed' ELSE 'active' END,s.created_at,coalesce(s.updated_at,s.created_at)
FROM smetra.support s
ON CONFLICT(id) DO NOTHING;
INSERT INTO smetra.conversation_members(conversation_id,user_id,role,joined_at,last_read_at)
SELECT s.conversation_id,s.user_id,'owner',s.created_at,0 FROM smetra.support s
WHERE s.conversation_id IS NOT NULL
ON CONFLICT(conversation_id,user_id) DO NOTHING;
INSERT INTO smetra.messages(id,conversation_id,sender_id,sender_role,body,payload,created_at)
SELECT 'support-first-' || s.id,s.conversation_id,s.user_id,'user',s.message,'{}'::jsonb,s.created_at
FROM smetra.support s
ON CONFLICT(id) DO NOTHING;
CREATE INDEX IF NOT EXISTS idx_support_status_updated ON smetra.support(status,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_human_open ON smetra.support(needs_human,status,updated_at DESC);

INSERT INTO smetra.conversations(id,kind,title,category,created_by,status,created_at,updated_at) VALUES
('community_general','community','Общий чат','general',NULL,'active',EXTRACT(EPOCH FROM NOW())::BIGINT,EXTRACT(EPOCH FROM NOW())::BIGINT),
('community_finishing','community','Отделка','finishing',NULL,'active',EXTRACT(EPOCH FROM NOW())::BIGINT,EXTRACT(EPOCH FROM NOW())::BIGINT),
('community_electrical','community','Электрика','electrical',NULL,'active',EXTRACT(EPOCH FROM NOW())::BIGINT,EXTRACT(EPOCH FROM NOW())::BIGINT),
('community_plumbing','community','Сантехника','plumbing',NULL,'active',EXTRACT(EPOCH FROM NOW())::BIGINT,EXTRACT(EPOCH FROM NOW())::BIGINT),
('community_subcontract','community','Биржа субподряда','subcontract',NULL,'active',EXTRACT(EPOCH FROM NOW())::BIGINT,EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT(id) DO NOTHING;

-- All communication remains server-authenticated. These policies are defense in depth for
-- the custom Smetra session context used by the backend and do not expose user email.
GRANT SELECT(public_id,role,created_at) ON smetra.users TO smetra_runtime;
ALTER TABLE smetra.user_directory ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.user_directory FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.conversations FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.conversation_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.conversation_members FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.direct_chat_pairs ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.direct_chat_pairs FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.messages FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_directory_public_read ON smetra.user_directory;
CREATE POLICY user_directory_public_read ON smetra.user_directory FOR SELECT
USING (visible OR user_id=(SELECT smetra.runtime_user_id()));
DROP POLICY IF EXISTS user_directory_self_insert ON smetra.user_directory;
CREATE POLICY user_directory_self_insert ON smetra.user_directory FOR INSERT
WITH CHECK (user_id=(SELECT smetra.runtime_user_id()));
DROP POLICY IF EXISTS user_directory_self_update ON smetra.user_directory;
CREATE POLICY user_directory_self_update ON smetra.user_directory FOR UPDATE
USING (user_id=(SELECT smetra.runtime_user_id()))
WITH CHECK (user_id=(SELECT smetra.runtime_user_id()));

DROP POLICY IF EXISTS conversations_member_read ON smetra.conversations;
CREATE POLICY conversations_member_read ON smetra.conversations FOR SELECT
USING (
  kind='community' OR created_by=(SELECT smetra.runtime_user_id()) OR
  EXISTS (SELECT 1 FROM smetra.conversation_members cm
          WHERE cm.conversation_id=conversations.id AND cm.user_id=(SELECT smetra.runtime_user_id())) OR
  (kind='support' AND EXISTS (SELECT 1 FROM smetra.users u
                               WHERE u.id=(SELECT smetra.runtime_user_id()) AND u.role='admin'))
);
DROP POLICY IF EXISTS conversations_creator_insert ON smetra.conversations;
CREATE POLICY conversations_creator_insert ON smetra.conversations FOR INSERT
WITH CHECK (created_by=(SELECT smetra.runtime_user_id()));
DROP POLICY IF EXISTS conversations_member_update ON smetra.conversations;
CREATE POLICY conversations_member_update ON smetra.conversations FOR UPDATE
USING (created_by=(SELECT smetra.runtime_user_id()) OR EXISTS(
  SELECT 1 FROM smetra.conversation_members cm WHERE cm.conversation_id=conversations.id
  AND cm.user_id=(SELECT smetra.runtime_user_id()) AND cm.role IN ('owner','admin')))
WITH CHECK (created_by=(SELECT smetra.runtime_user_id()) OR EXISTS(
  SELECT 1 FROM smetra.conversation_members cm WHERE cm.conversation_id=conversations.id
  AND cm.user_id=(SELECT smetra.runtime_user_id()) AND cm.role IN ('owner','admin')));

DROP POLICY IF EXISTS conversation_members_read ON smetra.conversation_members;
CREATE POLICY conversation_members_read ON smetra.conversation_members FOR SELECT
USING (user_id=(SELECT smetra.runtime_user_id()));
DROP POLICY IF EXISTS conversation_members_insert ON smetra.conversation_members;
CREATE POLICY conversation_members_insert ON smetra.conversation_members FOR INSERT
WITH CHECK (
  user_id=(SELECT smetra.runtime_user_id()) OR EXISTS(
    SELECT 1 FROM smetra.conversations c WHERE c.id=conversation_members.conversation_id
      AND c.created_by=(SELECT smetra.runtime_user_id())
  ) OR EXISTS(
    SELECT 1 FROM smetra.conversations c JOIN smetra.users u ON u.id=(SELECT smetra.runtime_user_id())
      WHERE c.id=conversation_members.conversation_id AND c.kind='support' AND u.role='admin'
  )
);
DROP POLICY IF EXISTS conversation_members_update_self ON smetra.conversation_members;
CREATE POLICY conversation_members_update_self ON smetra.conversation_members FOR UPDATE
USING (user_id=(SELECT smetra.runtime_user_id()))
WITH CHECK (user_id=(SELECT smetra.runtime_user_id()));

DROP POLICY IF EXISTS direct_chat_pairs_read ON smetra.direct_chat_pairs;
CREATE POLICY direct_chat_pairs_read ON smetra.direct_chat_pairs FOR SELECT
USING (user_low=(SELECT smetra.runtime_user_id()) OR user_high=(SELECT smetra.runtime_user_id()));
DROP POLICY IF EXISTS direct_chat_pairs_insert ON smetra.direct_chat_pairs;
CREATE POLICY direct_chat_pairs_insert ON smetra.direct_chat_pairs FOR INSERT
WITH CHECK (user_low=(SELECT smetra.runtime_user_id()) OR user_high=(SELECT smetra.runtime_user_id()));

DROP POLICY IF EXISTS messages_member_read ON smetra.messages;
CREATE POLICY messages_member_read ON smetra.messages FOR SELECT
USING (
  EXISTS (SELECT 1 FROM smetra.conversation_members cm
          WHERE cm.conversation_id=messages.conversation_id AND cm.user_id=(SELECT smetra.runtime_user_id())) OR
  EXISTS (SELECT 1 FROM smetra.conversations c JOIN smetra.users u ON u.id=(SELECT smetra.runtime_user_id())
          WHERE c.id=messages.conversation_id AND c.kind='support' AND u.role='admin')
);
DROP POLICY IF EXISTS messages_member_insert ON smetra.messages;
CREATE POLICY messages_member_insert ON smetra.messages FOR INSERT
WITH CHECK (
  (sender_id=(SELECT smetra.runtime_user_id()) OR sender_role='ai' AND sender_id IS NULL OR sender_role='system' AND sender_id IS NULL) AND
  (EXISTS (SELECT 1 FROM smetra.conversation_members cm
           WHERE cm.conversation_id=messages.conversation_id AND cm.user_id=(SELECT smetra.runtime_user_id())) OR
   EXISTS (SELECT 1 FROM smetra.conversations c JOIN smetra.users u ON u.id=(SELECT smetra.runtime_user_id())
           WHERE c.id=messages.conversation_id AND c.kind='support' AND u.role='admin'))
);
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.user_directory,smetra.conversations,smetra.conversation_members,smetra.direct_chat_pairs,smetra.messages TO service_role,postgres,smetra_runtime;

DO $realtime$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname='supabase_realtime') THEN
    BEGIN EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE smetra.conversations'; EXCEPTION WHEN duplicate_object THEN NULL; END;
    BEGIN EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE smetra.conversation_members'; EXCEPTION WHEN duplicate_object THEN NULL; END;
    BEGIN EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE smetra.messages'; EXCEPTION WHEN duplicate_object THEN NULL; END;
  END IF;
END
$realtime$;

INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(49,EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT(version) DO NOTHING;
COMMIT;
