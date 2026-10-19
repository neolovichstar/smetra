BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- Preserve the source of an estimate across edits, revisions and PDF exports.
ALTER TABLE smetra.quotes
    ADD COLUMN IF NOT EXISTS ai_generated BIGINT NOT NULL DEFAULT 0
    CHECK (ai_generated IN (0,1));

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (37, extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
