-- Migration applied directly to Supabase; stored here for reproducibility.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE smetra.billing_intents
  ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES smetra.workspaces(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS auto_renew_requested BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS renewal_consent_at BIGINT,
  ADD COLUMN IF NOT EXISTS renewal_consent_version TEXT,
  ADD COLUMN IF NOT EXISTS subscription_id TEXT REFERENCES smetra.billing_subscriptions(id) ON DELETE SET NULL;

ALTER TABLE smetra.workspaces
  ADD COLUMN IF NOT EXISTS smart_supplier_until BIGINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_billing_intents_workspace
  ON smetra.billing_intents(workspace_id) WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_intents_subscription
  ON smetra.billing_intents(subscription_id) WHERE subscription_id IS NOT NULL;

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (42, EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT (version) DO NOTHING;

COMMIT;

