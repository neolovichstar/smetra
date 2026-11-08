-- Version 68: isolated, server-side recurring billing. No payment card numbers or CVV.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.billing_autopay_contracts (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL UNIQUE REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 plan_code TEXT NOT NULL CHECK(plan_code IN ('pro_month','pro_year','pro_plus_month','pro_plus_year','team_month','team_year')),
 amount_kopecks BIGINT NOT NULL CHECK(amount_kopecks>0),
 duration_days BIGINT NOT NULL CHECK(duration_days IN (31,366)),
 status TEXT NOT NULL CHECK(status IN ('pending','active','canceled','unlinked','paused')),
 method_ciphertext TEXT,
 pending_method_ciphertext TEXT,
 method_type TEXT,
 method_last4 TEXT,
 consent_version TEXT NOT NULL,
 consent_at BIGINT NOT NULL,
 next_charge_at BIGINT,
 link_expires_at BIGINT,
 lease_until BIGINT NOT NULL DEFAULT 0,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 canceled_at BIGINT
);
CREATE INDEX IF NOT EXISTS idx_billing_autopay_due ON smetra.billing_autopay_contracts(status,next_charge_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_billing_autopay_user ON smetra.billing_autopay_contracts(user_id,workspace_id);
CREATE TABLE IF NOT EXISTS smetra.billing_autopay_attempts (
 id TEXT PRIMARY KEY,
 contract_id TEXT NOT NULL REFERENCES smetra.billing_autopay_contracts(id) ON DELETE CASCADE,
 due_at BIGINT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('prepared','pending','succeeded','canceled','failed')),
 provider_payment_id TEXT UNIQUE,
 payment_id TEXT UNIQUE REFERENCES smetra.payments(id) ON DELETE SET NULL,
 started_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 UNIQUE(contract_id,due_at)
);
ALTER TABLE smetra.billing_autopay_contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.billing_autopay_contracts FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.billing_autopay_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.billing_autopay_attempts FORCE ROW LEVEL SECURITY;
-- These tables are exclusively served by the authenticated application backend,
-- not exposed through PostgREST or the lower privilege runtime connection.
REVOKE ALL ON smetra.billing_autopay_contracts,smetra.billing_autopay_attempts FROM PUBLIC,anon,authenticated,smetra_runtime;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(68,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;