-- Partner catalog Unicode casefold field; indexed for later prefix search.
-- Deployment gated on version 63; backfill existing rows via PostgreSQL Unicode lower().
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.partner_products
 ADD COLUMN IF NOT EXISTS search_name text NOT NULL DEFAULT '';
UPDATE smetra.partner_products
 SET search_name=lower(name)
 WHERE search_name='';
CREATE INDEX IF NOT EXISTS idx_partner_products_partner_search
 ON smetra.partner_products(partner_id,search_name);
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(63,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
