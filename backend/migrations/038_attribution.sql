-- First-touch marketing attribution: which campaign or site brought each new account.
CREATE TABLE IF NOT EXISTS user_attribution (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  source TEXT NOT NULL DEFAULT '',
  medium TEXT NOT NULL DEFAULT '',
  campaign TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  term TEXT NOT NULL DEFAULT '',
  referrer_host TEXT NOT NULL DEFAULT '',
  landing_path TEXT NOT NULL DEFAULT '',
  first_seen_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_user_attribution_source ON user_attribution(source, medium, campaign);
