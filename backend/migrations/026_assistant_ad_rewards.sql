CREATE TABLE IF NOT EXISTS assistant_ad_rewards (
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 reward_date TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount=3),
 remaining INTEGER NOT NULL CHECK(remaining>=0 AND remaining<=amount),
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 UNIQUE(user_id,reward_date)
);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_rewards_user_expiry
 ON assistant_ad_rewards(user_id,expires_at,created_at);
INSERT OR IGNORE INTO schema_migrations(version,applied_at)
VALUES (40, strftime('%s','now'));
