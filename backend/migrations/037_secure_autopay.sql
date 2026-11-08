CREATE TABLE IF NOT EXISTS billing_autopay_contracts (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL UNIQUE REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 plan_code TEXT NOT NULL,
 amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks>0),
 duration_days INTEGER NOT NULL CHECK(duration_days IN (31,366)),
 status TEXT NOT NULL CHECK(status IN ('pending','active','canceled','unlinked','paused')),
 method_ciphertext TEXT,
 pending_method_ciphertext TEXT,
 method_type TEXT,
 method_last4 TEXT,
 consent_version TEXT NOT NULL,
 consent_at INTEGER NOT NULL,
 next_charge_at INTEGER,
 link_expires_at INTEGER,
 lease_until INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 canceled_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_billing_autopay_due ON billing_autopay_contracts(status,next_charge_at,lease_until);
CREATE INDEX IF NOT EXISTS idx_billing_autopay_user ON billing_autopay_contracts(user_id,workspace_id);
CREATE TABLE IF NOT EXISTS billing_autopay_attempts (
 id TEXT PRIMARY KEY,
 contract_id TEXT NOT NULL REFERENCES billing_autopay_contracts(id) ON DELETE CASCADE,
 due_at INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('prepared','pending','succeeded','canceled','failed')),
 provider_payment_id TEXT UNIQUE,
 payment_id TEXT UNIQUE REFERENCES payments(id) ON DELETE SET NULL,
 started_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 UNIQUE(contract_id,due_at)
);