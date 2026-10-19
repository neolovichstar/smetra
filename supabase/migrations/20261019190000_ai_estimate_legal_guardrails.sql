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

COMMIT;
