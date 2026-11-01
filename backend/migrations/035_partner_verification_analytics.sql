-- Additional verification, partner-reported telemetry and expiring console sessions.
CREATE TABLE IF NOT EXISTS partner_domain_verifications (
 partner_id TEXT PRIMARY KEY REFERENCES partner_accounts(id) ON DELETE CASCADE,
 domain TEXT NOT NULL, token TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','verified')),
 method TEXT NOT NULL CHECK(method IN ('dns','meta')),
 verified_at INTEGER, last_checked_at INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS partner_site_events (
 id TEXT PRIMARY KEY,
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id) ON DELETE CASCADE,
 event_key TEXT NOT NULL,
 event_type TEXT NOT NULL CHECK(event_type IN ('widget_impression','widget_click','material_order_reported')),
 amount_kopecks INTEGER NOT NULL DEFAULT 0 CHECK(amount_kopecks>=0),
 created_at INTEGER NOT NULL,
 UNIQUE(partner_id,event_key)
);
CREATE INDEX IF NOT EXISTS idx_partner_site_events_analytics ON partner_site_events(partner_id,created_at,event_type);
CREATE TABLE IF NOT EXISTS partner_console_sessions (
 id TEXT PRIMARY KEY,
 partner_id TEXT NOT NULL REFERENCES partner_accounts(id) ON DELETE CASCADE,
 session_hash TEXT NOT NULL UNIQUE,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 revoked_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_partner_sessions_expires ON partner_console_sessions(expires_at);
