-- Add the fixed public subscription catalog and included marketplace access.
-- Rebuild the constrained table additively while preserving all historical subscription data.
PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;
BEGIN IMMEDIATE;

ALTER TABLE billing_subscriptions RENAME TO billing_subscriptions_legacy_v1;
CREATE TABLE billing_subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
  product_code TEXT NOT NULL CHECK(product_code IN (
    'pro_solo_month','pro_solo_year','pro_plus_month',
    'pro_team_month','pro_team_year','smart_supplier_month'
  )),
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
  CHECK (
    (product_code IN ('pro_team_month','pro_team_year') AND workspace_id IS NOT NULL)
    OR (product_code NOT IN ('pro_team_month','pro_team_year') AND workspace_id IS NULL)
  ),
  CHECK (
    auto_renew = 0 OR
    (renewal_consent_at IS NOT NULL AND renewal_consent_version IS NOT NULL
     AND provider_payment_method_id IS NOT NULL AND provider IN ('yookassa','rustore'))
  )
);
INSERT INTO billing_subscriptions(
  id,user_id,workspace_id,product_code,provider,provider_subscription_id,
  provider_payment_method_id,amount_kopecks,currency,status,auto_renew,
  renewal_consent_at,renewal_consent_version,current_period_start,current_period_end,
  next_charge_at,cancel_at_period_end,canceled_at,last_payment_id,created_at,updated_at
)
SELECT id,user_id,workspace_id,product_code,provider,provider_subscription_id,
       provider_payment_method_id,amount_kopecks,currency,status,auto_renew,
       renewal_consent_at,renewal_consent_version,current_period_start,current_period_end,
       next_charge_at,cancel_at_period_end,canceled_at,last_payment_id,created_at,updated_at
FROM billing_subscriptions_legacy_v1;
DROP TABLE billing_subscriptions_legacy_v1;

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

CREATE TABLE IF NOT EXISTS lead_access_grants (
  id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES marketplace_leads(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
  idempotency_key TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(lead_id,user_id),
  UNIQUE(user_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_lead_access_grants_user_time
  ON lead_access_grants(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_access_grants_workspace_time
  ON lead_access_grants(workspace_id,created_at DESC)
  WHERE workspace_id IS NOT NULL;
INSERT OR IGNORE INTO lead_access_grants(id,lead_id,user_id,workspace_id,idempotency_key,created_at)
SELECT id,lead_id,buyer_user_id,buyer_workspace_id,'legacy:' || id,purchased_at
FROM lead_purchases;
INSERT OR IGNORE INTO schema_migrations(version,applied_at)
VALUES(34,CAST(strftime('%s','now') AS INTEGER));

UPDATE workspaces SET seat_limit=5 WHERE plan='pro_team' AND seat_limit>5;

COMMIT;
PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
