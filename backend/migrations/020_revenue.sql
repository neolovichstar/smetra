CREATE TABLE IF NOT EXISTS pricing_assignments (
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, experiment TEXT NOT NULL,
 variant TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(user_id,experiment)
);
CREATE TABLE IF NOT EXISTS growth_events (
 id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
 name TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', variant TEXT NOT NULL DEFAULT '',
 dedupe_key TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_growth_user ON growth_events(user_id,name,created_at);
CREATE INDEX IF NOT EXISTS idx_growth_name ON growth_events(name,created_at);
CREATE TABLE IF NOT EXISTS billing_intents (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), request_key TEXT NOT NULL,
 plan TEXT NOT NULL, amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks>0),
 duration_days INTEGER NOT NULL CHECK(duration_days>0), variant TEXT NOT NULL, source TEXT NOT NULL,
 is_test INTEGER NOT NULL CHECK(is_test IN (0,1)), payment_id TEXT UNIQUE REFERENCES payments(id),
 created_at INTEGER NOT NULL, UNIQUE(user_id,request_key)
);
CREATE INDEX IF NOT EXISTS idx_billing_intents_time ON billing_intents(is_test,created_at);
CREATE TABLE IF NOT EXISTS referral_links (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, code TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS referral_rewards (
 invitee_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 inviter_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 bonus INTEGER NOT NULL CHECK(bonus>0), period TEXT NOT NULL, rewarded_at INTEGER
);
