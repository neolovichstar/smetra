-- Durable idempotency records for scheduled recurrent charges.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

CREATE TABLE IF NOT EXISTS smetra.billing_renewal_attempts (
  id TEXT PRIMARY KEY,
  subscription_id TEXT NOT NULL REFERENCES smetra.billing_subscriptions(id) ON DELETE CASCADE,
  period_end BIGINT NOT NULL,
  attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
  idempotency_key TEXT NOT NULL UNIQUE,
  payment_id TEXT REFERENCES smetra.payments(id) ON DELETE SET NULL,
  provider_payment_id TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'prepared'
    CHECK (status IN ('prepared','pending','succeeded','failed','needs_action','canceled')),
  started_at BIGINT NOT NULL,
  finished_at BIGINT,
  last_error_code TEXT,
  UNIQUE (subscription_id, period_end, attempt_no)
);
CREATE INDEX IF NOT EXISTS idx_billing_renewal_attempts_subscription
  ON smetra.billing_renewal_attempts(subscription_id, period_end DESC, attempt_no DESC);
CREATE INDEX IF NOT EXISTS idx_billing_renewal_attempts_status
  ON smetra.billing_renewal_attempts(status, started_at DESC);
ALTER TABLE smetra.billing_renewal_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.billing_renewal_attempts FORCE ROW LEVEL SECURITY;
INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (43, EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT (version) DO NOTHING;
COMMIT;
