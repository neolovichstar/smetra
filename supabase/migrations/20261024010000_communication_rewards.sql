BEGIN;
-- Communication center / online presence, private Smetra schema.
-- Roll-forward-only. Browser access is routed through the authenticated API.
CREATE TABLE IF NOT EXISTS smetra.chat_conversations (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('direct','object','estimate','support','community')),
  subject TEXT NOT NULL DEFAULT '',
  workspace_id TEXT NOT NULL DEFAULT '',
  project_id TEXT NOT NULL DEFAULT '',
  quote_id TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  community_key TEXT UNIQUE,
  direct_key TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','waiting','closed')),
  needs_human INTEGER NOT NULL DEFAULT 0 CHECK (needs_human IN (0,1)),
  human_reason TEXT NOT NULL DEFAULT '',
  assigned_admin_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
  created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS smetra.chat_members (
  conversation_id TEXT NOT NULL REFERENCES smetra.chat_conversations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member',
  joined_at BIGINT NOT NULL,
  last_read_at BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (conversation_id,user_id)
);
CREATE TABLE IF NOT EXISTS smetra.chat_messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES smetra.chat_conversations(id) ON DELETE CASCADE,
  sender_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
  sender_type TEXT NOT NULL CHECK (sender_type IN ('user','assistant','admin','system')),
  body TEXT NOT NULL CHECK (length(body) <= 4000),
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS smetra.app_presence (
  user_id TEXT PRIMARY KEY REFERENCES smetra.users(id) ON DELETE CASCADE,
  last_seen_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_member_user ON smetra.chat_members(user_id,joined_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation ON smetra.chat_messages(conversation_id,created_at,id);
CREATE INDEX IF NOT EXISTS idx_chat_support_queue ON smetra.chat_conversations(kind,needs_human,status,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_presence_seen ON smetra.app_presence(last_seen_at DESC);
ALTER TABLE smetra.chat_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.chat_conversations FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.chat_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.chat_members FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.chat_messages FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.app_presence ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.app_presence FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.chat_conversations FROM PUBLIC, anon, authenticated;
REVOKE ALL ON smetra.chat_members FROM PUBLIC, anon, authenticated;
REVOKE ALL ON smetra.chat_messages FROM PUBLIC, anon, authenticated;
REVOKE ALL ON smetra.app_presence FROM PUBLIC, anon, authenticated;
ALTER TABLE smetra.billing_subscriptions ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE smetra.assistant_jobs ADD COLUMN IF NOT EXISTS ad_reward_id TEXT;
CREATE INDEX IF NOT EXISTS idx_reward_credit_expiry ON smetra.assistant_ad_reward_credits(user_id,expires_at);
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(51,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
