BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

ALTER TABLE smetra.oauth_states
    ADD COLUMN IF NOT EXISTS registration_intent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE smetra.oauth_states
    ADD COLUMN IF NOT EXISTS legal_acceptance BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE smetra.oauth_states
    ADD COLUMN IF NOT EXISTS legal_version TEXT NOT NULL DEFAULT '';

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (36, extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
