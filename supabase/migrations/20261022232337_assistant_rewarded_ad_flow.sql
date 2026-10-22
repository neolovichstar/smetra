-- One-time nonce, server-owned reward credit and per-period reservation accounting.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.assistant_ad_attempts (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  nonce_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued','completed','expired','rejected')),
  created_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL,
  completed_at BIGINT,
  CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_attempts_user_created
  ON smetra.assistant_ad_attempts(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_attempts_expiry
  ON smetra.assistant_ad_attempts(expires_at) WHERE status='issued';
CREATE TABLE IF NOT EXISTS smetra.assistant_ad_reward_credits (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  attempt_id TEXT NOT NULL UNIQUE REFERENCES smetra.assistant_ad_attempts(id) ON DELETE RESTRICT,
  reward_date TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 3 CHECK (amount=3),
  remaining INTEGER NOT NULL DEFAULT 3 CHECK (remaining BETWEEN 0 AND amount),
  created_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL,
  CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_credit_user_expiry
  ON smetra.assistant_ad_reward_credits(user_id,expires_at,created_at);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_credit_expiry
  ON smetra.assistant_ad_reward_credits(expires_at) WHERE remaining>0;
CREATE TABLE IF NOT EXISTS smetra.assistant_ad_reward_usage (
  quota_key TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  count INTEGER NOT NULL DEFAULT 0 CHECK (count>=0),
  updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_reward_usage_user
  ON smetra.assistant_ad_reward_usage(user_id,updated_at DESC);
ALTER TABLE smetra.assistant_jobs
  ADD COLUMN IF NOT EXISTS ad_reward_id TEXT REFERENCES smetra.assistant_ad_reward_credits(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_assistant_jobs_ad_reward
  ON smetra.assistant_jobs(ad_reward_id) WHERE ad_reward_id IS NOT NULL;
ALTER TABLE smetra.assistant_ad_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_ad_attempts FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_ad_reward_credits ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_ad_reward_credits FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_ad_reward_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_ad_reward_usage FORCE ROW LEVEL SECURITY;
INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(45,EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT(version) DO NOTHING;
COMMIT;
