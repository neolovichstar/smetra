CREATE TABLE IF NOT EXISTS native_web_tickets (
 ticket_hash TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_native_web_tickets_expiry ON native_web_tickets(expires_at);
