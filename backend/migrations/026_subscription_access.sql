-- Paid product subscriptions and workspace entitlements (SQLite runtime).
CREATE TABLE IF NOT EXISTS billing_subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  product_code TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_subscription_id TEXT NOT NULL UNIQUE,
  provider_payment_method_id TEXT NOT NULL DEFAULT '',
  amount_kopecks INTEGER NOT NULL CHECK (amount_kopecks >= 0),
  currency TEXT NOT NULL DEFAULT 'RUB',
  status TEXT NOT NULL DEFAULT 'pending',
  is_test INTEGER NOT NULL DEFAULT 0 CHECK (is_test IN (0,1)),
  auto_renew INTEGER NOT NULL DEFAULT 0 CHECK (auto_renew IN (0,1)),
  renewal_consent_at INTEGER,
  renewal_consent_version TEXT,
  current_period_start INTEGER NOT NULL DEFAULT 0,
  current_period_end INTEGER NOT NULL DEFAULT 0,
  next_charge_at INTEGER,
  cancel_at_period_end INTEGER NOT NULL DEFAULT 0 CHECK (cancel_at_period_end IN (0,1)),
  canceled_at INTEGER,
  last_payment_id TEXT REFERENCES payments(id) ON DELETE SET NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_workspace_access
  ON billing_subscriptions(workspace_id,status,current_period_end DESC);
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_user_access
  ON billing_subscriptions(user_id,status,current_period_end DESC);

INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(29,CAST(strftime('%s','now') AS INTEGER));
