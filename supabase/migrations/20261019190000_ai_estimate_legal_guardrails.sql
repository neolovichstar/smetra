BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

ALTER TABLE smetra.users
    ADD COLUMN IF NOT EXISTS terms_accepted_at BIGINT NOT NULL DEFAULT 0;
ALTER TABLE smetra.users
    ADD COLUMN IF NOT EXISTS terms_version TEXT NOT NULL DEFAULT '';
ALTER TABLE smetra.oauth_states
    ADD COLUMN IF NOT EXISTS terms_accepted_at BIGINT NOT NULL DEFAULT 0;
ALTER TABLE smetra.oauth_states
    ADD COLUMN IF NOT EXISTS terms_version TEXT NOT NULL DEFAULT '';
ALTER TABLE smetra.quotes
    ADD COLUMN IF NOT EXISTS ai_generated BIGINT NOT NULL DEFAULT 0;

-- Existing installations may have these columns from an earlier partial rollout;
-- ADD COLUMN IF NOT EXISTS does not repair defaults on a column that already exists.
ALTER TABLE smetra.users
    ALTER COLUMN terms_accepted_at SET DEFAULT 0;
ALTER TABLE smetra.users
    ALTER COLUMN terms_version SET DEFAULT '';
ALTER TABLE smetra.oauth_states
    ALTER COLUMN terms_accepted_at SET DEFAULT 0;
ALTER TABLE smetra.oauth_states
    ALTER COLUMN terms_version SET DEFAULT '';
ALTER TABLE smetra.quotes
    ALTER COLUMN ai_generated SET DEFAULT 0;

COMMIT;
