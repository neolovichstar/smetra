BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE IF NOT EXISTS smetra.assistant_ad_rewards (
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 reward_date TEXT NOT NULL,
 amount BIGINT NOT NULL CHECK(amount=3),
 remaining BIGINT NOT NULL CHECK(remaining>=0 AND remaining<=amount),
 created_at BIGINT NOT NULL,
 expires_at BIGINT NOT NULL,
 UNIQUE(user_id,reward_date)
);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_rewards_user_expiry
 ON smetra.assistant_ad_rewards(user_id,expires_at,created_at);

ALTER TABLE smetra.assistant_ad_rewards ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_ad_rewards FORCE ROW LEVEL SECURITY;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.assistant_ad_rewards TO smetra_runtime;
REVOKE ALL ON smetra.assistant_ad_rewards FROM PUBLIC,anon,authenticated;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname='smetra' AND tablename='assistant_ad_rewards'
      AND policyname='smetra_runtime_assistant_ad_rewards'
  ) THEN
    CREATE POLICY smetra_runtime_assistant_ad_rewards
      ON smetra.assistant_ad_rewards FOR ALL TO smetra_runtime
      USING (user_id=smetra.runtime_user_id())
      WITH CHECK (user_id=smetra.runtime_user_id());
  END IF;
END $$;
INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES (40,extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
