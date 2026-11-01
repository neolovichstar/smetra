-- Partner program is private. No anonymous or client Data API grants.
-- Apply before enabling the partner API; do not run on page startup.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.partner_accounts (
 id text PRIMARY KEY, code text NOT NULL UNIQUE, name text NOT NULL,
 allowed_host text NOT NULL, active bigint NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 commission_bps bigint NOT NULL DEFAULT 2000 CHECK(commission_bps BETWEEN 0 AND 3000),
 term_days bigint NOT NULL DEFAULT 365 CHECK(term_days BETWEEN 30 AND 730),
 created_at bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS smetra.partner_api_tokens (
 id text PRIMARY KEY,
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id) ON DELETE CASCADE,
 token_hash text NOT NULL UNIQUE, created_at bigint NOT NULL, revoked_at bigint
);
CREATE TABLE IF NOT EXISTS smetra.partner_clicks (
 id text PRIMARY KEY,
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id) ON DELETE CASCADE,
 token_hash text NOT NULL UNIQUE, created_at bigint NOT NULL, expires_at bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_partner_clicks_age ON smetra.partner_clicks(expires_at);
CREATE TABLE IF NOT EXISTS smetra.partner_attributions (
 user_id text PRIMARY KEY REFERENCES smetra.users(id) ON DELETE CASCADE,
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id),
 click_id text NOT NULL UNIQUE REFERENCES smetra.partner_clicks(id),
 rate_bps bigint NOT NULL CHECK(rate_bps BETWEEN 0 AND 3000),
 term_days bigint NOT NULL CHECK(term_days BETWEEN 30 AND 730),
 created_at bigint NOT NULL, first_paid_at bigint
);
CREATE INDEX IF NOT EXISTS idx_partner_attributions_partner ON smetra.partner_attributions(partner_id,created_at);
CREATE TABLE IF NOT EXISTS smetra.partner_commissions (
 id text PRIMARY KEY,
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id),
 user_id text NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 payment_id text NOT NULL UNIQUE REFERENCES smetra.payments(id),
 gross_kopecks bigint NOT NULL CHECK(gross_kopecks>0),
 commission_kopecks bigint NOT NULL CHECK(commission_kopecks>0),
 rate_bps bigint NOT NULL CHECK(rate_bps BETWEEN 1 AND 3000),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','reversed')),
 created_at bigint NOT NULL, ready_at bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_partner_commissions_partner ON smetra.partner_commissions(partner_id,status,created_at DESC);
CREATE TABLE IF NOT EXISTS smetra.partner_products (
 id text PRIMARY KEY,
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id) ON DELETE CASCADE,
 sku text NOT NULL, name text NOT NULL,
 price_kopecks bigint NOT NULL CHECK(price_kopecks>=0),
 url text NOT NULL, available bigint NOT NULL DEFAULT 1 CHECK(available IN (0,1)),
 updated_at bigint NOT NULL, UNIQUE(partner_id,sku)
);
CREATE INDEX IF NOT EXISTS idx_partner_products_available ON smetra.partner_products(available,price_kopecks);
CREATE TABLE IF NOT EXISTS smetra.partner_outbound_clicks (
 id text PRIMARY KEY,
 partner_id text NOT NULL REFERENCES smetra.partner_accounts(id),
 product_id text NOT NULL REFERENCES smetra.partner_products(id),
 user_id text REFERENCES smetra.users(id) ON DELETE SET NULL,
 created_at bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_partner_outbound_age ON smetra.partner_outbound_clicks(partner_id,created_at DESC);
DO $private$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['partner_accounts','partner_api_tokens','partner_clicks',
  'partner_attributions','partner_commissions','partner_products','partner_outbound_clicks'] LOOP
  EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC, anon, authenticated, smetra_runtime',t);
 END LOOP;
END $private$;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(61,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
