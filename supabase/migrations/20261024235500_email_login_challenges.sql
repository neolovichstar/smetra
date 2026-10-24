BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.email_login_challenges (
 id TEXT PRIMARY KEY,
 email TEXT NOT NULL,
 code_hash TEXT NOT NULL,
 intent TEXT NOT NULL CHECK(intent IN ('register','login')),
 name TEXT NOT NULL DEFAULT '',
 legal_version TEXT NOT NULL DEFAULT '',
 attempts BIGINT NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
 expires_at BIGINT NOT NULL,
 created_at BIGINT NOT NULL,
 consumed_at BIGINT
);
CREATE INDEX IF NOT EXISTS idx_email_login_email ON smetra.email_login_challenges(email,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_login_expiration ON smetra.email_login_challenges(expires_at);
ALTER TABLE smetra.email_login_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.email_login_challenges FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.email_login_challenges FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.email_login_challenges TO smetra_runtime;
-- Authentication challenges operate before a user belongs to a workspace.
-- Access only via the private server runtime role; deny PostgREST/client access.
CREATE POLICY email_challenges_runtime ON smetra.email_login_challenges
 FOR ALL TO smetra_runtime USING(true) WITH CHECK(true);
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(53,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
