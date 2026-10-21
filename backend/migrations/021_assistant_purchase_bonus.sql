CREATE TABLE IF NOT EXISTS assistant_bonus_grants (
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 payment_id TEXT NOT NULL UNIQUE REFERENCES payments(id) ON DELETE CASCADE,
 amount INTEGER NOT NULL CHECK(amount>=0),
 remaining INTEGER NOT NULL CHECK(remaining>=0 AND remaining<=amount),
 expires_at INTEGER NOT NULL,
 created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_bonus_user_expiry
 ON assistant_bonus_grants(user_id,expires_at,created_at);
CREATE TABLE IF NOT EXISTS assistant_bonus_usage (
 quota_key TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 count INTEGER NOT NULL DEFAULT 0 CHECK(count>=0),
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_bonus_usage_user
 ON assistant_bonus_usage(user_id,updated_at);
