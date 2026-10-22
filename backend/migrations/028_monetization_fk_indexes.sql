-- SQLite/local counterpart for monetization foreign-key indexes.
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_marketplace_product ON affiliate_clicks(marketplace_product_id);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_quote_item ON affiliate_clicks(quote_item_id);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_workspace ON affiliate_clicks(workspace_id) WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_renewal_attempts_payment ON billing_renewal_attempts(payment_id) WHERE payment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_last_payment ON billing_subscriptions(last_payment_id) WHERE last_payment_id IS NOT NULL;
INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(31,CAST(strftime('%s','now') AS INTEGER));
