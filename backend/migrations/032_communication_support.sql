-- Communication, support chat and public user directory.
-- SQLite/local migration version 35.
PRAGMA foreign_keys = ON;

ALTER TABLE users ADD COLUMN public_id TEXT;
UPDATE users
SET public_id='SM-' || upper(substr(replace(id,'-',''),1,16))
WHERE public_id IS NULL OR public_id='';
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_public_id ON users(public_id);

CREATE TABLE IF NOT EXISTS user_directory (
  public_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  profession TEXT NOT NULL DEFAULT '',
  company TEXT NOT NULL DEFAULT '',
  visible INTEGER NOT NULL DEFAULT 1 CHECK(visible IN (0,1)),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE TRIGGER IF NOT EXISTS trg_users_public_directory_after_insert
AFTER INSERT ON users
BEGIN
  UPDATE users SET public_id=CASE
    WHEN NEW.public_id IS NULL OR NEW.public_id='' THEN 'SM-' || upper(substr(hex(randomblob(8)),1,16))
    ELSE NEW.public_id END
  WHERE id=NEW.id;
  INSERT INTO user_directory(public_id,user_id,display_name,profession,company,visible,created_at,updated_at)
  VALUES((SELECT public_id FROM users WHERE id=NEW.id),NEW.id,NEW.name,'','',1,NEW.created_at,0)
  ON CONFLICT(user_id) DO UPDATE SET public_id=excluded.public_id,display_name=excluded.display_name;
END;

INSERT INTO user_directory(public_id,user_id,display_name,profession,company,visible,created_at,updated_at)
SELECT u.public_id,u.id,u.name,coalesce(p.profession,''),coalesce(p.company,''),1,u.created_at,coalesce(p.updated_at,0)
FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id
ON CONFLICT(user_id) DO NOTHING;
CREATE INDEX IF NOT EXISTS idx_user_directory_name ON user_directory(lower(display_name));
CREATE INDEX IF NOT EXISTS idx_user_directory_profession ON user_directory(lower(profession));

ALTER TABLE support ADD COLUMN subject TEXT NOT NULL DEFAULT 'Вопрос в поддержку';
ALTER TABLE support ADD COLUMN needs_human INTEGER NOT NULL DEFAULT 0 CHECK(needs_human IN (0,1));
ALTER TABLE support ADD COLUMN conversation_id TEXT;
ALTER TABLE support ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0;
ALTER TABLE support ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('low','normal','high','urgent'));
ALTER TABLE support ADD COLUMN ai_state TEXT NOT NULL DEFAULT 'active' CHECK(ai_state IN ('active','human','resolved'));
ALTER TABLE support ADD COLUMN assigned_admin_id TEXT REFERENCES users(id) ON DELETE SET NULL;
UPDATE support SET updated_at=created_at WHERE updated_at=0;

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('direct','quote','workspace','community','support')),
  title TEXT NOT NULL DEFAULT '',
  workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
  quote_id TEXT REFERENCES quotes(id) ON DELETE CASCADE,
  object_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  category TEXT NOT NULL DEFAULT '',
  created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','closed','archived')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_quote ON conversations(quote_id)
  WHERE kind='quote' AND quote_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_workspace_object ON conversations(workspace_id,coalesce(object_id,''))
  WHERE kind='workspace' AND workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations(workspace_id,kind,updated_at DESC);

CREATE TABLE IF NOT EXISTS conversation_members (
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('owner','member','customer','admin','participant')),
  joined_at INTEGER NOT NULL,
  last_read_at INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(conversation_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_conversation_members_user ON conversation_members(user_id,joined_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_members_conversation ON conversation_members(conversation_id,user_id);

CREATE TABLE IF NOT EXISTS direct_chat_pairs (
  user_low TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  user_high TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id TEXT NOT NULL UNIQUE REFERENCES conversations(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  PRIMARY KEY(user_low,user_high),
  CHECK(user_low < user_high)
);
CREATE INDEX IF NOT EXISTS idx_direct_chat_pairs_high ON direct_chat_pairs(user_high,user_low);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  sender_role TEXT NOT NULL CHECK(sender_role IN ('user','admin','ai','system')),
  body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 4000),
  payload TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL,
  edited_at INTEGER,
  deleted_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id,created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS idx_messages_sender_created ON messages(sender_id,created_at DESC) WHERE sender_id IS NOT NULL;

-- Upgrade existing one-message support submissions to chat threads without losing their content.
INSERT INTO conversations(id,kind,title,created_by,status,created_at,updated_at)
SELECT 'support-' || s.id,'support',coalesce(nullif(s.subject,''),'Вопрос в поддержку'),s.user_id,
       CASE WHEN s.status='closed' THEN 'closed' ELSE 'active' END,s.created_at,coalesce(s.updated_at,s.created_at)
FROM support s
WHERE s.conversation_id IS NULL;
UPDATE support SET conversation_id='support-' || id WHERE conversation_id IS NULL;
INSERT INTO conversation_members(conversation_id,user_id,role,joined_at,last_read_at)
SELECT s.conversation_id,s.user_id,'owner',s.created_at,0
FROM support s
WHERE s.conversation_id IS NOT NULL
ON CONFLICT(conversation_id,user_id) DO NOTHING;
INSERT INTO messages(id,conversation_id,sender_id,sender_role,body,payload,created_at)
SELECT 'support-first-' || s.id,s.conversation_id,s.user_id,'user',s.message,'{}',s.created_at
FROM support s
WHERE s.conversation_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.id='support-first-' || s.id);
CREATE INDEX IF NOT EXISTS idx_support_status_updated ON support(status,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_human_open ON support(needs_human,status,updated_at DESC);

INSERT OR IGNORE INTO schema_migrations(version,applied_at)
VALUES(35,CAST(strftime('%s','now') AS INTEGER));
