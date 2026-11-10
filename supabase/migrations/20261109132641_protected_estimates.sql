-- Version 72: immutable protected estimate links, minimal view analytics and verified decisions.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS protection_enabled BIGINT NOT NULL DEFAULT 0 CHECK(protection_enabled IN (0,1));
CREATE UNIQUE INDEX IF NOT EXISTS idx_quotes_identity_workspace ON smetra.quotes(id,workspace_id);
CREATE TABLE IF NOT EXISTS smetra.protected_quote_links (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 quote_id TEXT NOT NULL REFERENCES smetra.quotes(id) ON DELETE CASCADE,
 quote_version BIGINT NOT NULL,
 snapshot_sha256 TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,
 request_key_hash TEXT NOT NULL DEFAULT '',
 request_hash TEXT NOT NULL DEFAULT '',
 recipient_name TEXT NOT NULL DEFAULT '',
 recipient_email TEXT NOT NULL DEFAULT '',
 contractor_name TEXT NOT NULL,
 settings TEXT NOT NULL,
 access_code_hash TEXT NOT NULL DEFAULT '',
 access_epoch BIGINT NOT NULL DEFAULT 1,
 expires_at BIGINT NOT NULL,
 max_views BIGINT CHECK(max_views IS NULL OR max_views BETWEEN 1 AND 10000),
 view_count BIGINT NOT NULL DEFAULT 0 CHECK(view_count>=0),
 first_viewed_at BIGINT,
 last_viewed_at BIGINT,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
 proposal_state TEXT NOT NULL DEFAULT 'sent' CHECK(proposal_state IN ('sent','viewed','changes_requested','approved','rejected')),
 revision BIGINT NOT NULL DEFAULT 1,
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 revoked_at BIGINT,
 FOREIGN KEY(quote_id,quote_version) REFERENCES smetra.quote_versions(quote_id,version) ON DELETE CASCADE,
 FOREIGN KEY(quote_id,workspace_id) REFERENCES smetra.quotes(id,workspace_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_protected_links_identity_workspace ON smetra.protected_quote_links(id,workspace_id);
CREATE INDEX IF NOT EXISTS idx_protected_links_quote ON smetra.protected_quote_links(workspace_id,quote_id,created_at DESC,id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_protected_links_request ON smetra.protected_quote_links(workspace_id,created_by,request_key_hash) WHERE request_key_hash<>'';
CREATE INDEX IF NOT EXISTS idx_protected_links_quote_id ON smetra.protected_quote_links(quote_id);
CREATE INDEX IF NOT EXISTS idx_protected_links_creator ON smetra.protected_quote_links(created_by);
CREATE TABLE IF NOT EXISTS smetra.protected_quote_views (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 link_id TEXT NOT NULL REFERENCES smetra.protected_quote_links(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL UNIQUE,
 access_epoch BIGINT NOT NULL,
 ordinal BIGINT NOT NULL CHECK(ordinal>0),
 created_at BIGINT NOT NULL,
 expires_at BIGINT NOT NULL,
 FOREIGN KEY(link_id,workspace_id) REFERENCES smetra.protected_quote_links(id,workspace_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_protected_views_link ON smetra.protected_quote_views(link_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_protected_views_expiry ON smetra.protected_quote_views(expires_at,id);
CREATE INDEX IF NOT EXISTS idx_protected_views_workspace ON smetra.protected_quote_views(workspace_id,link_id);
CREATE TABLE IF NOT EXISTS smetra.protected_quote_events (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 link_id TEXT NOT NULL REFERENCES smetra.protected_quote_links(id) ON DELETE CASCADE,
 kind TEXT NOT NULL,
 actor_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 detail TEXT NOT NULL DEFAULT '{}',
 created_at BIGINT NOT NULL,
 FOREIGN KEY(link_id,workspace_id) REFERENCES smetra.protected_quote_links(id,workspace_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_protected_events_link ON smetra.protected_quote_events(workspace_id,link_id,created_at DESC,id);
CREATE INDEX IF NOT EXISTS idx_protected_events_link_id ON smetra.protected_quote_events(link_id);
CREATE INDEX IF NOT EXISTS idx_protected_events_actor ON smetra.protected_quote_events(actor_id);
CREATE TABLE IF NOT EXISTS smetra.protected_quote_decisions (
 link_id TEXT PRIMARY KEY REFERENCES smetra.protected_quote_links(id) ON DELETE CASCADE,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 view_id TEXT NOT NULL,
 user_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 action TEXT NOT NULL CHECK(action IN ('approved','changes_requested','rejected')),
 comment TEXT NOT NULL DEFAULT '',
 quote_version BIGINT NOT NULL,
 snapshot_sha256 TEXT NOT NULL,
 created_at BIGINT NOT NULL,
 FOREIGN KEY(link_id,workspace_id) REFERENCES smetra.protected_quote_links(id,workspace_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_protected_decisions_workspace ON smetra.protected_quote_decisions(workspace_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_protected_decisions_user ON smetra.protected_quote_decisions(user_id);

ALTER TABLE smetra.protected_quote_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.protected_quote_links FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.protected_quote_links FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON smetra.protected_quote_links TO smetra_runtime;
CREATE POLICY protected_workspace_manager ON smetra.protected_quote_links FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id) AND EXISTS (SELECT 1 FROM smetra.workspace_members m WHERE m.workspace_id=protected_quote_links.workspace_id AND m.user_id=(SELECT smetra.runtime_user_id()) AND m.role IN ('owner','admin','manager'))) WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id) AND EXISTS (SELECT 1 FROM smetra.workspace_members m WHERE m.workspace_id=protected_quote_links.workspace_id AND m.user_id=(SELECT smetra.runtime_user_id()) AND m.role IN ('owner','admin','manager')));


ALTER TABLE smetra.protected_quote_views ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.protected_quote_views FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.protected_quote_views FROM PUBLIC,anon,authenticated;
GRANT SELECT ON smetra.protected_quote_views TO smetra_runtime;
CREATE POLICY protected_workspace_manager ON smetra.protected_quote_views FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id) AND EXISTS (SELECT 1 FROM smetra.workspace_members m WHERE m.workspace_id=protected_quote_views.workspace_id AND m.user_id=(SELECT smetra.runtime_user_id()) AND m.role IN ('owner','admin','manager'))) WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id) AND EXISTS (SELECT 1 FROM smetra.workspace_members m WHERE m.workspace_id=protected_quote_views.workspace_id AND m.user_id=(SELECT smetra.runtime_user_id()) AND m.role IN ('owner','admin','manager')));


ALTER TABLE smetra.protected_quote_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.protected_quote_events FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.protected_quote_events FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON smetra.protected_quote_events TO smetra_runtime;
CREATE POLICY protected_workspace_manager ON smetra.protected_quote_events FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id) AND EXISTS (SELECT 1 FROM smetra.workspace_members m WHERE m.workspace_id=protected_quote_events.workspace_id AND m.user_id=(SELECT smetra.runtime_user_id()) AND m.role IN ('owner','admin','manager'))) WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id) AND EXISTS (SELECT 1 FROM smetra.workspace_members m WHERE m.workspace_id=protected_quote_events.workspace_id AND m.user_id=(SELECT smetra.runtime_user_id()) AND m.role IN ('owner','admin','manager')));


ALTER TABLE smetra.protected_quote_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.protected_quote_decisions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.protected_quote_decisions FROM PUBLIC,anon,authenticated;
GRANT SELECT ON smetra.protected_quote_decisions TO smetra_runtime;
CREATE POLICY protected_workspace_manager ON smetra.protected_quote_decisions FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id) AND EXISTS (SELECT 1 FROM smetra.workspace_members m WHERE m.workspace_id=protected_quote_decisions.workspace_id AND m.user_id=(SELECT smetra.runtime_user_id()) AND m.role IN ('owner','admin','manager'))) WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id) AND EXISTS (SELECT 1 FROM smetra.workspace_members m WHERE m.workspace_id=protected_quote_decisions.workspace_id AND m.user_id=(SELECT smetra.runtime_user_id()) AND m.role IN ('owner','admin','manager')));
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(72,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
