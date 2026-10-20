BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- Persist the server-owned estimate origin and make AI draft claims atomic.
ALTER TABLE smetra.quotes
    ADD COLUMN IF NOT EXISTS ai_generated BIGINT NOT NULL DEFAULT 0
    CHECK (ai_generated IN (0,1));

ALTER TABLE smetra.ai_usage
    ADD COLUMN IF NOT EXISTS draft_claimed_at BIGINT;

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (37, extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
