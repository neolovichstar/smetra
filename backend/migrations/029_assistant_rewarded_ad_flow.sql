-- Server-side attempts and consumable credits for Yandex rewarded-ad callbacks.
CREATE TABLE IF NOT EXISTS assistant_ad_attempts (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  nonce_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'issued' CHECK(status IN ('issued','completed','expired','rejected')),
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  completed_at INTEGER,
  CHECK(expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_attempts_user_created
  ON assistant_ad_attempts(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_attempts_expiry
  ON assistant_ad_attempts(expires_at) WHERE status='issued';

CREATE TABLE IF NOT EXISTS assistant_ad_reward_credits (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  attempt_id TEXT NOT NULL UNIQUE REFERENCES assistant_ad_attempts(id) ON DELETE CASCADE,
  reward_date TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 3 CHECK(amount=3),
  remaining INTEGER NOT NULL DEFAULT 3 CHECK(remaining BETWEEN 0 AND amount),
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  CHECK(expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_credit_user_expiry
  ON assistant_ad_reward_credits(user_id,expires_at,created_at);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_credit_expiry
  ON assistant_ad_reward_credits(expires_at) WHERE remaining>0;

CREATE TABLE IF NOT EXISTS assistant_ad_reward_usage (
  quota_key TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  count INTEGER NOT NULL DEFAULT 0 CHECK(count>=0),
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_ad_reward_usage_user
  ON assistant_ad_reward_usage(user_id,updated_at DESC);

INSERT OR IGNORE INTO schema_migrations(version,applied_at)
VALUES(32,CAST(strftime('%s','now') AS INTEGER));
