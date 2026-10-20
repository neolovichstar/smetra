BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

ALTER TABLE smetra.users
    ADD COLUMN IF NOT EXISTS terms_accepted_at BIGINT;
ALTER TABLE smetra.users
    ADD COLUMN IF NOT EXISTS terms_version TEXT;

ALTER TABLE smetra.quotes
    ADD COLUMN IF NOT EXISTS ai_generated BIGINT NOT NULL DEFAULT 0
    CHECK (ai_generated IN (0, 1));

-- The runtime can read the consent version and update only the two consent
-- columns. The UPDATE RLS policy remains restricted to the verified session.
GRANT SELECT (terms_accepted_at, terms_version)
    ON smetra.users TO smetra_runtime;
GRANT UPDATE (terms_accepted_at, terms_version)
    ON smetra.users TO smetra_runtime;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'smetra'
          AND tablename = 'users'
          AND policyname = 'smetra_runtime_legal_acceptance'
    ) THEN
        CREATE POLICY smetra_runtime_legal_acceptance
            ON smetra.users
            FOR UPDATE
            TO smetra_runtime
            USING (id = smetra.runtime_user_id())
            WITH CHECK (id = smetra.runtime_user_id());
    END IF;
END
$$;

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (35, extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
