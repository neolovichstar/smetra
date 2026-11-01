-- Apply explicitly before enabling partner console version 2.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.partner_domain_verifications (
 partner_id text PRIMARY KEY REFERENCES smetra.partner_accounts(id) ON DELETE CASCADE,
 domain text NOT NULL, token text NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','verified')),
 method text NOT NULL CHECK(method IN ('dns','meta')),
 verified_at bigint, last_checked_at bigint, created_at bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS smetra.partner_site_events (
 id text PRIMARY KEY,
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id) ON DELETE CASCADE,
 event_key text NOT NULL,
 event_type text NOT NULL CHECK(event_type IN ('widget_impression','widget_click','material_order_reported')),
 amount_kopecks bigint NOT NULL DEFAULT 0 CHECK(amount_kopecks>=0),
 created_at bigint NOT NULL,
 UNIQUE(partner_id,event_key)
);
CREATE INDEX IF NOT EXISTS idx_partner_site_events_analytics ON smetra.partner_site_events(partner_id,created_at,event_type);
CREATE TABLE IF NOT EXISTS smetra.partner_console_sessions (
 id text PRIMARY KEY,
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id) ON DELETE CASCADE,
 session_hash text NOT NULL UNIQUE,
 created_at bigint NOT NULL,
 expires_at bigint NOT NULL,
 revoked_at bigint
);
CREATE INDEX IF NOT EXISTS idx_partner_sessions_expires ON smetra.partner_console_sessions(expires_at);
DO $private$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['partner_domain_verifications','partner_site_events','partner_console_sessions'] LOOP
  EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC,anon,authenticated,smetra_runtime',t);
 END LOOP;
END $private$;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(62,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
