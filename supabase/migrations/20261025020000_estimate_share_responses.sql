BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.estimate_shares (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 quote_id TEXT NOT NULL REFERENCES smetra.quotes(id) ON DELETE CASCADE,
 quote_version BIGINT NOT NULL,
 sender_user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 recipient_email TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'active',
 expires_at BIGINT NOT NULL,
 created_at BIGINT NOT NULL,
 revoked_at BIGINT NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_estimate_shares_active
 ON smetra.estimate_shares(workspace_id,quote_id,quote_version,recipient_email) WHERE status='active';
ALTER TABLE smetra.estimate_shares ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.estimate_shares FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.estimate_shares FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.estimate_shares TO smetra_runtime;
CREATE POLICY smetra_runtime_scope ON smetra.estimate_shares FOR ALL TO smetra_runtime
 USING(workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK(workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id));
CREATE INDEX IF NOT EXISTS idx_estimate_shares_recipient
 ON smetra.estimate_shares(recipient_email,status,created_at DESC);
CREATE TABLE IF NOT EXISTS smetra.estimate_share_responses (
 share_id text PRIMARY KEY REFERENCES smetra.estimate_shares(id) ON DELETE CASCADE,
 recipient_user_id text NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 selected_optional text NOT NULL DEFAULT '[]',
 total_kopecks bigint NOT NULL CHECK(total_kopecks>=0),
 status text NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','changes_requested')),
 revision bigint NOT NULL DEFAULT 1,
 updated_at bigint NOT NULL
);
ALTER TABLE smetra.estimate_share_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.estimate_share_responses FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.estimate_share_responses FROM PUBLIC,anon,authenticated;
-- Recipient-side access only through authorized first-party API using private
-- server connection. Runtime writers cannot grant themselves recipient access.
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(55,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
