CREATE TABLE IF NOT EXISTS estimate_shares (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 quote_id TEXT NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
 quote_version INTEGER NOT NULL,
 sender_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 recipient_email TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'active',
 expires_at INTEGER NOT NULL,created_at INTEGER NOT NULL,revoked_at INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_estimate_shares_active
 ON estimate_shares(workspace_id,quote_id,quote_version,recipient_email) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_estimate_shares_recipient
 ON estimate_shares(recipient_email,status,created_at DESC);
CREATE TABLE IF NOT EXISTS estimate_share_responses (
 share_id TEXT PRIMARY KEY REFERENCES estimate_shares(id) ON DELETE CASCADE,
 recipient_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 selected_optional TEXT NOT NULL DEFAULT '[]',
 total_kopecks INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft',
 revision INTEGER NOT NULL DEFAULT 1,
 updated_at INTEGER NOT NULL
);
