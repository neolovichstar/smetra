-- Restore purchase-bonus tables and grant scoped runtime access to new reward tables.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.assistant_bonus_grants (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  payment_id TEXT NOT NULL UNIQUE REFERENCES smetra.payments(id) ON DELETE CASCADE,
  amount BIGINT NOT NULL CHECK(amount>=0),
  remaining BIGINT NOT NULL CHECK(remaining>=0 AND remaining<=amount),
  expires_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_bonus_user_expiry ON smetra.assistant_bonus_grants(user_id,expires_at,created_at);
CREATE TABLE IF NOT EXISTS smetra.assistant_bonus_usage (
  quota_key TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  count BIGINT NOT NULL DEFAULT 0 CHECK(count>=0),
  updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_bonus_usage_user ON smetra.assistant_bonus_usage(user_id,updated_at);
ALTER TABLE smetra.assistant_jobs ADD COLUMN IF NOT EXISTS bonus_grant_id TEXT REFERENCES smetra.assistant_bonus_grants(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_assistant_jobs_bonus_grant ON smetra.assistant_jobs(bonus_grant_id) WHERE bonus_grant_id IS NOT NULL;
ALTER TABLE smetra.assistant_bonus_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_bonus_grants FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_bonus_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_bonus_usage FORCE ROW LEVEL SECURITY;
GRANT SELECT, UPDATE ON smetra.assistant_bonus_grants TO smetra_runtime;
GRANT SELECT, INSERT, UPDATE ON smetra.assistant_bonus_usage TO smetra_runtime;
GRANT SELECT, INSERT, UPDATE ON smetra.assistant_ad_attempts TO smetra_runtime;
GRANT SELECT, INSERT, UPDATE ON smetra.assistant_ad_reward_credits TO smetra_runtime;
GRANT SELECT, INSERT, UPDATE ON smetra.assistant_ad_reward_usage TO smetra_runtime;
DO $policies$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='smetra' AND tablename='assistant_bonus_grants' AND policyname='smetra_runtime_bonus_grants') THEN
    CREATE POLICY smetra_runtime_bonus_grants ON smetra.assistant_bonus_grants FOR ALL TO smetra_runtime USING(user_id=(SELECT smetra.runtime_user_id())) WITH CHECK(user_id=(SELECT smetra.runtime_user_id()));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='smetra' AND tablename='assistant_bonus_usage' AND policyname='smetra_runtime_bonus_usage') THEN
    CREATE POLICY smetra_runtime_bonus_usage ON smetra.assistant_bonus_usage FOR ALL TO smetra_runtime USING(user_id=(SELECT smetra.runtime_user_id())) WITH CHECK(user_id=(SELECT smetra.runtime_user_id()));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='smetra' AND tablename='assistant_ad_attempts' AND policyname='smetra_runtime_ad_attempts') THEN
    CREATE POLICY smetra_runtime_ad_attempts ON smetra.assistant_ad_attempts FOR ALL TO smetra_runtime USING(user_id=(SELECT smetra.runtime_user_id())) WITH CHECK(user_id=(SELECT smetra.runtime_user_id()));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='smetra' AND tablename='assistant_ad_reward_credits' AND policyname='smetra_runtime_ad_credits') THEN
    CREATE POLICY smetra_runtime_ad_credits ON smetra.assistant_ad_reward_credits FOR ALL TO smetra_runtime USING(user_id=(SELECT smetra.runtime_user_id())) WITH CHECK(user_id=(SELECT smetra.runtime_user_id()));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='smetra' AND tablename='assistant_ad_reward_usage' AND policyname='smetra_runtime_ad_usage') THEN
    CREATE POLICY smetra_runtime_ad_usage ON smetra.assistant_ad_reward_usage FOR ALL TO smetra_runtime USING(user_id=(SELECT smetra.runtime_user_id())) WITH CHECK(user_id=(SELECT smetra.runtime_user_id()));
  END IF;
END
$policies$;
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(47,EXTRACT(EPOCH FROM NOW())::BIGINT) ON CONFLICT(version) DO NOTHING;
COMMIT;
