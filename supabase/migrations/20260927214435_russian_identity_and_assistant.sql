BEGIN;
CREATE TABLE IF NOT EXISTS smetra.external_identities (
 provider TEXT NOT NULL, subject TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 created_at BIGINT NOT NULL, PRIMARY KEY(provider,subject)
);
CREATE INDEX IF NOT EXISTS idx_external_identity_user ON smetra.external_identities(user_id);
CREATE TABLE IF NOT EXISTS smetra.oauth_states (
 state_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, verifier TEXT NOT NULL,
 browser_hash TEXT NOT NULL, app_challenge TEXT NOT NULL DEFAULT '',
 link_user_id TEXT REFERENCES smetra.users(id) ON DELETE CASCADE, expires_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS smetra.oauth_tickets (
 ticket_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 challenge TEXT NOT NULL, expires_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS smetra.assistant_messages (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 role TEXT NOT NULL, content TEXT NOT NULL, created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_messages ON smetra.assistant_messages(workspace_id,user_id,created_at);
CREATE TABLE IF NOT EXISTS smetra.assistant_actions (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 tool TEXT NOT NULL, arguments TEXT NOT NULL, summary TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', result TEXT NOT NULL DEFAULT '{}',
 created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL
);
ALTER TABLE smetra.external_identities ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.external_identities FROM PUBLIC,anon,authenticated;
ALTER TABLE smetra.oauth_states ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.oauth_states FROM PUBLIC,anon,authenticated;
ALTER TABLE smetra.oauth_tickets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.oauth_tickets FROM PUBLIC,anon,authenticated;
ALTER TABLE smetra.assistant_messages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.assistant_messages FROM PUBLIC,anon,authenticated;
ALTER TABLE smetra.assistant_actions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.assistant_actions FROM PUBLIC,anon,authenticated;
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(5,EXTRACT(EPOCH FROM now())::BIGINT) ON CONFLICT DO NOTHING;
COMMIT;
