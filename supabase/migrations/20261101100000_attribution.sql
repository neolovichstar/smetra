-- First-touch marketing attribution per account (UTM tags, referring site, landing page).
-- Deployment gated on version 66. Additive only; server-only table.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.user_attribution (
 user_id text PRIMARY KEY REFERENCES smetra.users(id) ON DELETE CASCADE,
 source text NOT NULL DEFAULT '',
 medium text NOT NULL DEFAULT '',
 campaign text NOT NULL DEFAULT '',
 content text NOT NULL DEFAULT '',
 term text NOT NULL DEFAULT '',
 referrer_host text NOT NULL DEFAULT '',
 landing_path text NOT NULL DEFAULT '',
 first_seen_at bigint NOT NULL,
 created_at bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_attribution_source ON smetra.user_attribution(source, medium, campaign);
ALTER TABLE smetra.user_attribution ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.user_attribution FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.user_attribution FROM PUBLIC, anon, authenticated, smetra_runtime;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(66,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
