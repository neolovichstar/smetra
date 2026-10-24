BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON smetra.sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_email_tokens_expires ON smetra.email_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_states_expires ON smetra.oauth_states(expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_tickets_expires ON smetra.oauth_tickets(expires_at);
CREATE INDEX IF NOT EXISTS idx_rate_limits_started ON smetra.rate_limits(started);
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(54,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
