-- Migration applied directly to Supabase; stored here for reproducibility.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

-- Version 41: additive B2B billing, lead marketplace and procurement/affiliate primitives.
ALTER TABLE smetra.users
  ADD COLUMN IF NOT EXISTS lead_token_balance BIGINT NOT NULL DEFAULT 0;
ALTER TABLE smetra.users
  ADD COLUMN IF NOT EXISTS lead_token_balance_updated_at BIGINT NOT NULL DEFAULT 0;

ALTER TABLE smetra.workspaces
  ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free',
  ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'inactive',
  ADD COLUMN IF NOT EXISTS entitlement_until BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS seat_limit INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS smart_supplier_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE smetra.quote_items
  ADD COLUMN IF NOT EXISTS supplier_status TEXT NOT NULL DEFAULT 'not_started',
  ADD COLUMN IF NOT EXISTS marketplace_product_id TEXT,
  ADD COLUMN IF NOT EXISTS supplier_paid_kopecks BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS supplier_due_kopecks BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS supplier_notes TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS supplier_updated_at BIGINT NOT NULL DEFAULT 0;

DO $migration$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='users_lead_token_balance_nonnegative') THEN
    ALTER TABLE smetra.users ADD CONSTRAINT users_lead_token_balance_nonnegative CHECK (lead_token_balance >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='workspaces_plan_check') THEN
    ALTER TABLE smetra.workspaces ADD CONSTRAINT workspaces_plan_check CHECK (plan IN ('free','pro_team'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='workspaces_subscription_status_check') THEN
    ALTER TABLE smetra.workspaces ADD CONSTRAINT workspaces_subscription_status_check CHECK (subscription_status IN ('inactive','active','past_due','canceled','expired'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='workspaces_seat_limit_check') THEN
    ALTER TABLE smetra.workspaces ADD CONSTRAINT workspaces_seat_limit_check CHECK (seat_limit BETWEEN 1 AND 6);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='quote_items_supplier_status_check') THEN
    ALTER TABLE smetra.quote_items ADD CONSTRAINT quote_items_supplier_status_check CHECK (supplier_status IN ('not_started','requested','ordered','partially_paid','paid','received','canceled'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='quote_items_supplier_amounts_check') THEN
    ALTER TABLE smetra.quote_items ADD CONSTRAINT quote_items_supplier_amounts_check CHECK (supplier_paid_kopecks >= 0 AND supplier_due_kopecks >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='quote_items_marketplace_product_fk') THEN
    ALTER TABLE smetra.quote_items ADD CONSTRAINT quote_items_marketplace_product_fk
      FOREIGN KEY (marketplace_product_id) REFERENCES smetra.catalog_items(id) ON DELETE SET NULL;
  END IF;
END
$migration$;

CREATE INDEX IF NOT EXISTS idx_users_lead_token_balance ON smetra.users(id) WHERE lead_token_balance > 0;
CREATE INDEX IF NOT EXISTS idx_quote_items_marketplace_product ON smetra.quote_items(marketplace_product_id) WHERE marketplace_product_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quote_items_supplier_status ON smetra.quote_items(supplier_status) WHERE supplier_status <> 'not_started';
CREATE INDEX IF NOT EXISTS idx_workspaces_plan_status_until ON smetra.workspaces(plan, subscription_status, entitlement_until);

CREATE TABLE IF NOT EXISTS smetra.billing_subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  workspace_id TEXT REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
  product_code TEXT NOT NULL CHECK (product_code IN ('pro_solo_month','pro_solo_year','smart_supplier_month','pro_team_month')),
  provider TEXT NOT NULL CHECK (provider IN ('yookassa','rustore','manual')),
  provider_subscription_id TEXT,
  provider_payment_method_id TEXT,
  amount_kopecks BIGINT NOT NULL CHECK (amount_kopecks > 0),
  currency TEXT NOT NULL DEFAULT 'RUB' CHECK (currency = 'RUB'),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','active','past_due','cancel_at_period_end','canceled','expired')),
  auto_renew BOOLEAN NOT NULL DEFAULT FALSE,
  renewal_consent_at BIGINT,
  renewal_consent_version TEXT,
  current_period_start BIGINT NOT NULL DEFAULT 0,
  current_period_end BIGINT NOT NULL DEFAULT 0,
  next_charge_at BIGINT,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
  canceled_at BIGINT,
  last_payment_id TEXT REFERENCES smetra.payments(id) ON DELETE SET NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  CHECK ((product_code = 'pro_team_month' AND workspace_id IS NOT NULL) OR
         (product_code <> 'pro_team_month' AND workspace_id IS NULL)),
  CHECK (NOT auto_renew OR
         (renewal_consent_at IS NOT NULL AND renewal_consent_version IS NOT NULL AND
          provider_payment_method_id IS NOT NULL AND provider IN ('yookassa','rustore')))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_subscriptions_provider_id
  ON smetra.billing_subscriptions(provider, provider_subscription_id)
  WHERE provider_subscription_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_user_status
  ON smetra.billing_subscriptions(user_id, status, current_period_end DESC);
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_workspace_status
  ON smetra.billing_subscriptions(workspace_id, status, current_period_end DESC)
  WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_renewal_due
  ON smetra.billing_subscriptions(next_charge_at, id)
  WHERE auto_renew = TRUE AND status = 'active' AND cancel_at_period_end = FALSE;

CREATE TABLE IF NOT EXISTS smetra.subscription_events (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider IN ('yookassa','rustore','manual')),
  provider_event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  outcome TEXT NOT NULL DEFAULT 'received' CHECK (outcome IN ('received','processed','ignored','failed')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  received_at BIGINT NOT NULL,
  processed_at BIGINT,
  last_error_code TEXT,
  UNIQUE (provider, provider_event_id)
);
CREATE INDEX IF NOT EXISTS idx_subscription_events_outcome_received
  ON smetra.subscription_events(outcome, received_at);

-- Marketplace listing is separated from the private customer contact record.
CREATE TABLE IF NOT EXISTS smetra.marketplace_leads (
  id TEXT PRIMARY KEY,
  created_by TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  source_quote_id TEXT REFERENCES smetra.quotes(id) ON DELETE SET NULL,
  city TEXT NOT NULL,
  property_type TEXT NOT NULL DEFAULT 'apartment',
  area_sqm NUMERIC(12,2),
  budget_min_kopecks BIGINT,
  budget_max_kopecks BIGINT,
  description TEXT NOT NULL DEFAULT '',
  desired_start_date DATE,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','assigned','completed','canceled','expired')),
  published_at BIGINT,
  expires_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  CHECK (area_sqm IS NULL OR area_sqm > 0),
  CHECK (budget_min_kopecks IS NULL OR budget_min_kopecks >= 0),
  CHECK (budget_max_kopecks IS NULL OR budget_max_kopecks >= 0),
  CHECK (budget_min_kopecks IS NULL OR budget_max_kopecks IS NULL OR budget_max_kopecks >= budget_min_kopecks)
);
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_feed
  ON smetra.marketplace_leads(city, published_at DESC, id DESC)
  WHERE status = 'published';
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_expiry
  ON smetra.marketplace_leads(expires_at)
  WHERE status = 'published' AND expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_owner
  ON smetra.marketplace_leads(created_by, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_quote
  ON smetra.marketplace_leads(source_quote_id)
  WHERE source_quote_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS smetra.marketplace_lead_contacts (
  lead_id TEXT PRIMARY KEY REFERENCES smetra.marketplace_leads(id) ON DELETE CASCADE,
  contact_name TEXT NOT NULL,
  phone TEXT,
  email TEXT,
  preferred_contact_method TEXT NOT NULL DEFAULT 'phone' CHECK (preferred_contact_method IN ('phone','email','messenger')),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  CHECK (phone IS NOT NULL OR email IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_marketplace_lead_contacts_email
  ON smetra.marketplace_lead_contacts(email)
  WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS smetra.lead_purchases (
  id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES smetra.marketplace_leads(id) ON DELETE RESTRICT,
  buyer_user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  buyer_workspace_id TEXT REFERENCES smetra.workspaces(id) ON DELETE SET NULL,
  price_kopecks BIGINT NOT NULL DEFAULT 15000 CHECK (price_kopecks > 0),
  tokens_spent BIGINT NOT NULL DEFAULT 150 CHECK (tokens_spent > 0),
  idempotency_key TEXT NOT NULL,
  purchased_at BIGINT NOT NULL,
  UNIQUE (lead_id, buyer_user_id),
  UNIQUE (buyer_user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_lead_purchases_buyer_time
  ON smetra.lead_purchases(buyer_user_id, purchased_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_purchases_workspace_time
  ON smetra.lead_purchases(buyer_workspace_id, purchased_at DESC)
  WHERE buyer_workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_lead_purchases_lead_time
  ON smetra.lead_purchases(lead_id, purchased_at DESC);

CREATE TABLE IF NOT EXISTS smetra.lead_token_ledger (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  delta_tokens BIGINT NOT NULL CHECK (delta_tokens <> 0),
  balance_after BIGINT NOT NULL CHECK (balance_after >= 0),
  entry_type TEXT NOT NULL CHECK (entry_type IN ('purchase','topup','refund','adjustment','promotion')),
  source TEXT NOT NULL,
  source_id TEXT,
  idempotency_key TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_lead_token_ledger_user_time
  ON smetra.lead_token_ledger(user_id, created_at DESC, id);

CREATE TABLE IF NOT EXISTS smetra.affiliate_clicks (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  workspace_id TEXT REFERENCES smetra.workspaces(id) ON DELETE SET NULL,
  quote_item_id TEXT NOT NULL REFERENCES smetra.quote_items(id) ON DELETE CASCADE,
  marketplace_product_id TEXT NOT NULL REFERENCES smetra.catalog_items(id) ON DELETE RESTRICT,
  partner TEXT NOT NULL CHECK (partner IN ('leroy_merlin','petrovich','other')),
  partner_product_ref TEXT,
  outbound_url TEXT,
  attribution_token_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'clicked' CHECK (status IN ('clicked','ordered','approved','paid','rejected')),
  order_reference TEXT,
  order_amount_kopecks BIGINT,
  commission_bps INTEGER NOT NULL DEFAULT 300 CHECK (commission_bps BETWEEN 0 AND 10000),
  commission_kopecks BIGINT,
  clicked_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  CHECK (order_amount_kopecks IS NULL OR order_amount_kopecks >= 0),
  CHECK (commission_kopecks IS NULL OR commission_kopecks >= 0)
);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_user_time
  ON smetra.affiliate_clicks(user_id, clicked_at DESC);
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_order_ref
  ON smetra.affiliate_clicks(partner, order_reference)
  WHERE order_reference IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_affiliate_clicks_status_time
  ON smetra.affiliate_clicks(status, updated_at);

-- All new records are in the private application schema. Never expose payment
-- methods or lead contacts to the client/database runtime role.
ALTER TABLE smetra.billing_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.subscription_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.marketplace_leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.marketplace_lead_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.lead_purchases ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.lead_token_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.affiliate_clicks ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.marketplace_lead_contacts FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.billing_subscriptions FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.subscription_events FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.lead_purchases FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.lead_token_ledger FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.affiliate_clicks FORCE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE ON smetra.marketplace_leads TO smetra_runtime;
ALTER TABLE smetra.marketplace_leads FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_marketplace_feed ON smetra.marketplace_leads
  FOR SELECT TO smetra_runtime
  USING (status = 'published' OR created_by = (SELECT smetra.runtime_user_id()));
CREATE POLICY smetra_marketplace_create ON smetra.marketplace_leads
  FOR INSERT TO smetra_runtime
  WITH CHECK (created_by = (SELECT smetra.runtime_user_id()) AND status = 'draft');
CREATE POLICY smetra_marketplace_owner_update ON smetra.marketplace_leads
  FOR UPDATE TO smetra_runtime
  USING (created_by = (SELECT smetra.runtime_user_id()))
  WITH CHECK (created_by = (SELECT smetra.runtime_user_id()));

GRANT SELECT ON smetra.lead_purchases TO smetra_runtime;
CREATE POLICY smetra_lead_purchases_read_own ON smetra.lead_purchases
  FOR SELECT TO smetra_runtime
  USING (buyer_user_id = (SELECT smetra.runtime_user_id()));

GRANT SELECT ON smetra.lead_token_ledger TO smetra_runtime;
CREATE POLICY smetra_lead_token_ledger_read_own ON smetra.lead_token_ledger
  FOR SELECT TO smetra_runtime
  USING (user_id = (SELECT smetra.runtime_user_id()));

GRANT SELECT ON smetra.affiliate_clicks TO smetra_runtime;
CREATE POLICY smetra_affiliate_clicks_read_own ON smetra.affiliate_clicks
  FOR SELECT TO smetra_runtime
  USING (user_id = (SELECT smetra.runtime_user_id()));

-- Make migrations visible to the existing app's schema gate.
INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (41, EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT (version) DO NOTHING;

COMMIT;

