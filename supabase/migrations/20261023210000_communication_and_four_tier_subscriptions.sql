-- Communication center + four-tier subscription catalog / private Smetra schema.
-- Apply only after reviewing the matching backend release. No public Data API access is granted.
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

ALTER TABLE smetra.billing_subscriptions
  ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_real_access
  ON smetra.billing_subscriptions(workspace_id,status,current_period_end DESC)
  WHERE is_test=FALSE;

-- Preserve existing paid access through the catalog migration. Legacy records
-- are non-renewing and excluded from live-revenue/subscriber reporting.
INSERT INTO smetra.billing_subscriptions(
  id,user_id,workspace_id,product_code,provider,provider_subscription_id,
  provider_payment_method_id,amount_kopecks,currency,status,is_test,auto_renew,
  current_period_start,current_period_end,cancel_at_period_end,last_payment_id,
  created_at,updated_at
)
SELECT
  'legacy-' || w.id,u.id,w.id,'pro_month','legacy','legacy:' || w.id,
  '',0,'RUB','active',FALSE,FALSE,
  floor(extract(epoch FROM now()))::bigint,u.entitlement_until,FALSE,NULL,
  floor(extract(epoch FROM now()))::bigint,floor(extract(epoch FROM now()))::bigint
FROM smetra.users u
JOIN smetra.workspaces w ON w.owner_id=u.id
WHERE u.deleted_at IS NULL AND u.plan='pro'
  AND COALESCE(u.entitlement_until,0)>floor(extract(epoch FROM now()))::bigint
  AND NOT EXISTS (
    SELECT 1 FROM smetra.billing_subscriptions s
    WHERE s.workspace_id=w.id AND s.status IN ('active','succeeded')
      AND s.current_period_end>floor(extract(epoch FROM now()))::bigint
  )
ON CONFLICT(provider_subscription_id) DO NOTHING;

UPDATE smetra.workspaces w
SET plan='pro_solo',subscription_status='active',seat_limit=1,
    entitlement_until=u.entitlement_until
FROM smetra.users u
WHERE w.owner_id=u.id AND w.id IN (
  SELECT s.workspace_id FROM smetra.billing_subscriptions s
  WHERE s.provider='legacy' AND s.status='active'
    AND s.current_period_end>floor(extract(epoch FROM now()))::bigint
);

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
GRANT SELECT, INSERT, UPDATE, DELETE ON smetra.chat_conversations TO smetra_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON smetra.chat_members TO smetra_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON smetra.chat_messages TO smetra_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON smetra.app_presence TO smetra_runtime;
DROP POLICY IF EXISTS smetra_runtime_chat_conversations ON smetra.chat_conversations;
CREATE POLICY smetra_runtime_chat_conversations ON smetra.chat_conversations
  FOR ALL TO smetra_runtime USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS smetra_runtime_chat_members ON smetra.chat_members;
CREATE POLICY smetra_runtime_chat_members ON smetra.chat_members
  FOR ALL TO smetra_runtime USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS smetra_runtime_chat_messages ON smetra.chat_messages;
CREATE POLICY smetra_runtime_chat_messages ON smetra.chat_messages
  FOR ALL TO smetra_runtime USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS smetra_runtime_app_presence ON smetra.app_presence;
CREATE POLICY smetra_runtime_app_presence ON smetra.app_presence
  FOR ALL TO smetra_runtime USING (true) WITH CHECK (true);

INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(49,extract(epoch FROM now())::bigint),(50,extract(epoch FROM now())::bigint)
ON CONFLICT(version) DO NOTHING;
