-- Preserve normal account deletion behavior: remove an earned reward with its ad attempt.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.assistant_ad_reward_credits
  DROP CONSTRAINT IF EXISTS assistant_ad_reward_credits_attempt_id_fkey;
ALTER TABLE smetra.assistant_ad_reward_credits
  ADD CONSTRAINT assistant_ad_reward_credits_attempt_id_fkey
  FOREIGN KEY (attempt_id) REFERENCES smetra.assistant_ad_attempts(id) ON DELETE CASCADE;
INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(46,EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT(version) DO NOTHING;
COMMIT;
