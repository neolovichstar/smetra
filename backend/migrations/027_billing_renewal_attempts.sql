-- SQLite/local counterpart for durable scheduled renewals.
CREATE TABLE IF NOT EXISTS billing_renewal_attempts (
  id TEXT PRIMARY KEY,
  subscription_id TEXT NOT NULL REFERENCES billing_subscriptions(id) ON DELETE CASCADE,
  period_end INTEGER NOT NULL,
  attempt_no INTEGER NOT NULL CHECK(attempt_no >= 1),
  idempotency_key TEXT NOT NULL UNIQUE,
  payment_id TEXT REFERENCES payments(id) ON DELETE SET NULL,
  provider_payment_id TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'prepared' CHECK(status IN ('prepared','pending','succeeded','failed','needs_action','canceled')),
  started_at INTEGER NOT NULL,
  finished_at INTEGER,
  last_error_code TEXT,
  UNIQUE(subscription_id,period_end,attempt_no)
);
CREATE INDEX IF NOT EXISTS idx_billing_renewal_attempts_subscription
  ON billing_renewal_attempts(subscription_id,period_end DESC,attempt_no DESC);
CREATE INDEX IF NOT EXISTS idx_billing_renewal_attempts_status
  ON billing_renewal_attempts(status,started_at DESC);
INSERT OR IGNORE INTO schema_migrations(version,applied_at)
VALUES(30,CAST(strftime('%s','now') AS INTEGER));
