-- Partner console access through Smetra accounts: members, invitations and one-time sign-in codes.
-- Deployment gated on version 64. Additive only: no existing table changes except one nullable column.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.partner_members (
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id) ON DELETE CASCADE,
 user_id text NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 role text NOT NULL CHECK(role IN ('owner','admin','analyst','catalog')),
 invited_by text REFERENCES smetra.users(id) ON DELETE SET NULL,
 created_at bigint NOT NULL,
 PRIMARY KEY(partner_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_partner_members_user ON smetra.partner_members(user_id);
CREATE TABLE IF NOT EXISTS smetra.partner_invites (
 id text PRIMARY KEY,
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id) ON DELETE CASCADE,
 email text NOT NULL,
 role text NOT NULL CHECK(role IN ('owner','admin','analyst','catalog')),
 created_by text REFERENCES smetra.users(id) ON DELETE SET NULL,
 created_at bigint NOT NULL,
 expires_at bigint NOT NULL,
 accepted_at bigint,
 accepted_by text REFERENCES smetra.users(id) ON DELETE SET NULL,
 revoked_at bigint
);
CREATE INDEX IF NOT EXISTS idx_partner_invites_email ON smetra.partner_invites(email,accepted_at,revoked_at);
CREATE INDEX IF NOT EXISTS idx_partner_invites_partner ON smetra.partner_invites(partner_id,created_at);
CREATE TABLE IF NOT EXISTS smetra.partner_sso_codes (
 code_hash text PRIMARY KEY,
 user_id text NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 created_at bigint NOT NULL,
 expires_at bigint NOT NULL,
 used_at bigint
);
CREATE INDEX IF NOT EXISTS idx_partner_sso_codes_expires ON smetra.partner_sso_codes(expires_at);
ALTER TABLE smetra.partner_console_sessions ADD COLUMN IF NOT EXISTS user_id text REFERENCES smetra.users(id) ON DELETE CASCADE;
-- Server-only tables, same rule as the rest of the partner platform.
DO $private$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['partner_members','partner_invites','partner_sso_codes'] LOOP
  EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC, anon, authenticated, smetra_runtime',t);
 END LOOP;
END $private$;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(64,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
