-- SQLite/local counterpart of the B2B billing and marketplace schema.
-- Columns on existing tables are added idempotently by backend.business.migrate().
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS billing_subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
  product_code TEXT NOT NULL CHECK(product_code IN ('pro_solo_month','pro_solo_year','smart_supplier_month','pro_team_month')),
  provider TEXT NOT NULL CHECK(provider IN ('yookassa','rustore','manual')),
  provider_subscription_id TEXT,
  provider_payment_method_id TEXT,
  amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks > 0),
  currency TEXT NOT NULL DEFAULT 'RUB' CHECK(currency = 'RUB'),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','past_due','cancel_at_period_end','canceled','expired')),
  auto_renew INTEGER NOT NULL DEFAULT 0 CHECK(auto_renew IN (0,1)),
  renewal_consent_at INTEGER,
  renewal_consent_version TEXT,
  current_period_start INTEGER NOT NULL DEFAULT 0,
  current_period_end INTEGER NOT NULL DEFAULT 0,
  next_charge_at INTEGER,
  cancel_at_period_end INTEGER NOT NULL DEFAULT 0 CHECK(cancel_at_period_end IN (0,1)),
  canceled_at INTEGER,
  last_payment_id TEXT REFERENCES payments(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK ((product_code = 'pro_team_month' AND workspace_id IS NOT NULL) OR
         (product_code <> 'pro_team_month' AND workspace_id IS NULL)),
  CHECK (auto_renew = 0 OR
         (renewal_consent_at IS NOT NULL AND renewal_consent_version IS NOT NULL AND
          provider_payment_method_id IS NOT NULL AND provider IN ('yookassa','rustore')))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_subscriptions_provider_id
  ON billing_subscriptions(provider, provider_subscription_id)
  WHERE provider_subscription_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_user_status
  ON billing_subscriptions(user_id, status, current_period_end DESC);
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_workspace_status
  ON billing_subscriptions(workspace_id, status, current_period_end DESC)
  WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_renewal_due
  ON billing_subscriptions(next_charge_at, id)
  WHERE auto_renew = 1 AND status = 'active' AND cancel_at_period_end = 0;

CREATE TABLE IF NOT EXISTS subscription_events (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK(provider IN ('yookassa','rustore','manual')),
  provider_event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  outcome TEXT NOT NULL DEFAULT 'received' CHECK(outcome IN ('received','processed','ignored','failed')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
  received_at INTEGER NOT NULL,
  processed_at INTEGER,
  last_error_code TEXT,
  UNIQUE(provider, provider_event_id)
);
CREATE INDEX IF NOT EXISTS idx_subscription_events_outcome_received
  ON subscription_events(outcome, received_at);

CREATE TABLE IF NOT EXISTS marketplace_leads (
  id TEXT PRIMARY KEY,
  created_by TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_quote_id TEXT REFERENCES quotes(id) ON DELETE SET NULL,
  city TEXT NOT NULL,
  property_type TEXT NOT NULL DEFAULT 'apartment',
  area_sqm NUMERIC,
  budget_min_kopecks INTEGER,
  budget_max_kopecks INTEGER,
  description TEXT NOT NULL DEFAULT '',
  desired_start_date TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','assigned','completed','canceled','expired')),
  published_at INTEGER,
  expires_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK(area_sqm IS NULL OR area_sqm > 0),
  CHECK(budget_min_kopecks IS NULL OR budget_min_kopecks >= 0),
  CHECK(budget_max_kopecks IS NULL OR budget_max_kopecks >= 0),
  CHECK(budget_min_kopecks IS NULL OR budget_max_kopecks IS NULL OR budget_max_kopecks >= budget_min_kopecks)
);
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_feed
  ON marketplace_leads(city, published_at DESC, id DESC) WHERE status = 'published';
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_expiry
  ON marketplace_leads(expires_at) WHERE status = 'published' AND expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_owner
  ON marketplace_leads(created_by, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_quote
  ON marketplace_leads(source_quote_id) WHERE source_quote_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS marketplace_lead_contacts (
  lead_id TEXT PRIMARY KEY REFERENCES marketplace_leads(id) ON DELETE CASCADE,
  contact_name TEXT NOT NULL,
  phone TEXT,
  email TEXT,
  preferred_contact_method TEXT NOT NULL DEFAULT 'phone' CHECK(preferred_contact_method IN ('phone','email','messenger')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK(phone IS NOT NULL OR email IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_marketplace_lead_contacts_email
  ON marketplace_lead_contacts(email) WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS lead_purchases (
  id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES marketplace_leads(id) ON DELETE RESTRICT,
  buyer_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  buyer_workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
  price_kopecks INTEGER NOT NULL DEFAULT 15000 CHECK(price_kopecks > 0),
  tokens_spent INTEGER NOT NULL DEFAULT 150 CHECK(tokens_spent > 0),
  idempotency_key TEXT NOT NULL,
  purchased_at INTEGER NOT NULL,
  UNIQUE(lead_id, buyer_user_id),
  UNIQUE(buyer_user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_lead_purchases_buyer_time
  ON lead_purchases(buyer_user_id, purchased_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_purchases_workspace_time
  ON lead_purchases(buyer_workspace_id, purchased_at DESC) WHERE buyer_workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_lead_purchases_lead_time
  ON lead_purchases(lead_id, purchased_at DESC);

CREATE TABLE IF NOT EXISTS lead_token_ledger (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  delta_tokens INTEGER NOT NULL CHECK(delta_tokens <> 0),
  balance_after INTEGER NOT NULL CHECK(balance_after >= 0),
  entry_type TEXT NOT NULL CHECK(entry_type IN ('purchase','topup','refund','adjustment','promotion')),
  source TEXT NOT NULL,
  source_id TEXT,
  idempotency_key TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_lead_token_ledger_user_time
  ON lead_token_ledger(user_id, created_at DESC, id);

CREATE TABLE IF NOT EXISTS affiliate_clicks (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
  quote_item_id TEXT NOT NULL REFERENCES quote_items(id) ON DELETE CASCADE,
  marketplace_product_id TEXT NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
  partner TEXT NOT NULL CHECK(partner IN ('leroy_merlin','petrovich','other')),
  partner_product_ref TEXT,
  outbound_url TEXT,
  attribution_token_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'clicked' CHECK(status IN ('clicked','ordered','approved','paid','rejected')),
  order_reference TEXT,
  order_amount_kopecks INTEGER,
  commission_bps INTEGER NOT NULL DEFAULT 300 CHECK(commission_bps BETWEEN 0 AND 10000),
  commission_kopecks INTEGER,
  clicked_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  CHECK(order_amount_kopecks IS NULL OR order_amount_kopecks >= 0),
  CHECK(commission_kopecks IS NULL OR commission_kopecks >= 0)
);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_user_time
  ON affiliate_clicks(user_id, clicked_at DESC);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_order_ref
  ON affiliate_clicks(partner, order_reference) WHERE order_reference IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_status_time
  ON affiliate_clicks(status, updated_at);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES(29, CAST(strftime('%s','now') AS INTEGER));
