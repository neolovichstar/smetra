CREATE TABLE IF NOT EXISTS assistant_ad_attempts (
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 nonce_hash TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'issued',created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,completed_at INTEGER);
CREATE TABLE IF NOT EXISTS assistant_ad_reward_credits (
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 attempt_id TEXT NOT NULL REFERENCES assistant_ad_attempts(id),reward_date TEXT NOT NULL,
 amount INTEGER NOT NULL DEFAULT 3,remaining INTEGER NOT NULL DEFAULT 3,
 created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,UNIQUE(user_id,reward_date));
CREATE TABLE IF NOT EXISTS assistant_ad_reward_usage (
 quota_key TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 count INTEGER NOT NULL DEFAULT 0,updated_at INTEGER NOT NULL);
