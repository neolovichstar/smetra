-- Local test baseline for pre-repository tables/columns, with no production data.
-- Applied after revenue/AI workspace migrations and before the 2026-10-18 indexes.
CREATE TABLE smetra.native_web_tickets (
 ticket_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 expires_at BIGINT NOT NULL
);
CREATE TABLE smetra.billing_subscriptions (
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 workspace_id TEXT REFERENCES smetra.workspaces(id) ON DELETE CASCADE,product_code TEXT NOT NULL,
 provider TEXT NOT NULL,provider_subscription_id TEXT,provider_payment_method_id TEXT,
 amount_kopecks BIGINT NOT NULL CHECK(amount_kopecks>0),currency TEXT NOT NULL DEFAULT 'RUB',
 status TEXT NOT NULL DEFAULT 'pending',auto_renew BOOLEAN NOT NULL DEFAULT false,
 renewal_consent_at BIGINT,renewal_consent_version TEXT,current_period_start BIGINT NOT NULL DEFAULT 0,
 current_period_end BIGINT NOT NULL DEFAULT 0,next_charge_at BIGINT,
 cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,canceled_at BIGINT,
 last_payment_id TEXT REFERENCES smetra.payments(id) ON DELETE SET NULL,
 created_at BIGINT NOT NULL,updated_at BIGINT NOT NULL,is_test BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE smetra.quote_followups (
 id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 quote_id TEXT NOT NULL REFERENCES smetra.quotes(id) ON DELETE CASCADE,
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 due_date TEXT NOT NULL CHECK(length(due_date)=10),channel TEXT NOT NULL CHECK(channel IN('email','call','message')),
 message TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN('scheduled','done','cancelled')),
 created_at BIGINT NOT NULL,completed_at BIGINT
);
CREATE TABLE smetra.estimate_shares (
 id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 quote_id TEXT NOT NULL REFERENCES smetra.quotes(id) ON DELETE CASCADE,quote_version BIGINT NOT NULL,
 sender_user_id TEXT NOT NULL REFERENCES smetra.users(id),recipient_email TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'active' CHECK(status IN('active','revoked')),
 expires_at BIGINT NOT NULL,created_at BIGINT NOT NULL,revoked_at BIGINT NOT NULL DEFAULT 0,
 FOREIGN KEY(quote_id,quote_version) REFERENCES smetra.quote_versions(quote_id,version)
);
ALTER TABLE smetra.workspaces ADD COLUMN plan TEXT NOT NULL DEFAULT 'free',
 ADD COLUMN subscription_status TEXT NOT NULL DEFAULT 'inactive',
 ADD COLUMN entitlement_until BIGINT NOT NULL DEFAULT 0,ADD COLUMN seat_limit BIGINT NOT NULL DEFAULT 1;
ALTER TABLE smetra.billing_intents ADD COLUMN workspace_id TEXT REFERENCES smetra.workspaces(id) ON DELETE SET NULL;
