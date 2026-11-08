BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE smetra.native_web_tickets (
 ticket_hash TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 expires_at BIGINT NOT NULL
);
CREATE INDEX idx_native_web_tickets_expiry ON smetra.native_web_tickets(expires_at);
ALTER TABLE smetra.native_web_tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.native_web_tickets FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.native_web_tickets FROM PUBLIC,anon,authenticated,smetra_runtime;
INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(29,extract(epoch FROM now())::BIGINT) ON CONFLICT DO NOTHING;

COMMIT;
