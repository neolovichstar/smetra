-- Local dev: bounded maintenance scans of expired transient state.
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_email_tokens_expires ON email_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_states_expires ON oauth_states(expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_tickets_expires ON oauth_tickets(expires_at);
CREATE INDEX IF NOT EXISTS idx_rate_limits_started ON rate_limits(started);
