-- Add covering indexes for high-cardinality foreign keys in the monetization tables.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_marketplace_product ON smetra.affiliate_clicks(marketplace_product_id);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_quote_item ON smetra.affiliate_clicks(quote_item_id);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_workspace ON smetra.affiliate_clicks(workspace_id) WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_renewal_attempts_payment ON smetra.billing_renewal_attempts(payment_id) WHERE payment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_last_payment ON smetra.billing_subscriptions(last_payment_id) WHERE last_payment_id IS NOT NULL;
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(44,EXTRACT(EPOCH FROM NOW())::BIGINT) ON CONFLICT(version) DO NOTHING;
COMMIT;
