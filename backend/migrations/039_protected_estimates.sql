CREATE UNIQUE INDEX IF NOT EXISTS idx_quotes_identity_workspace ON quotes(id,workspace_id);
CREATE TABLE IF NOT EXISTS protected_quote_links (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 quote_id TEXT NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
 quote_version INTEGER NOT NULL,
 snapshot_sha256 TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,
 request_key_hash TEXT NOT NULL DEFAULT '',
 request_hash TEXT NOT NULL DEFAULT '',
 recipient_name TEXT NOT NULL DEFAULT '',
 recipient_email TEXT NOT NULL DEFAULT '',
 contractor_name TEXT NOT NULL,
 settings TEXT NOT NULL,
 access_code_hash TEXT NOT NULL DEFAULT '',
 access_epoch INTEGER NOT NULL DEFAULT 1,
 expires_at INTEGER NOT NULL,
 max_views INTEGER CHECK(max_views IS NULL OR max_views BETWEEN 1 AND 10000),
 view_count INTEGER NOT NULL DEFAULT 0 CHECK(view_count>=0),
 first_viewed_at INTEGER,
 last_viewed_at INTEGER,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
 proposal_state TEXT NOT NULL DEFAULT 'sent' CHECK(proposal_state IN ('sent','viewed','changes_requested','approved','rejected')),
 revision INTEGER NOT NULL DEFAULT 1,
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 revoked_at INTEGER,
 FOREIGN KEY(quote_id,quote_version) REFERENCES quote_versions(quote_id,version) ON DELETE CASCADE,
 FOREIGN KEY(quote_id,workspace_id) REFERENCES quotes(id,workspace_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_protected_links_identity_workspace ON protected_quote_links(id,workspace_id);
CREATE INDEX IF NOT EXISTS idx_protected_links_quote ON protected_quote_links(workspace_id,quote_id,created_at DESC,id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_protected_links_request ON protected_quote_links(workspace_id,created_by,request_key_hash) WHERE request_key_hash<>'';
CREATE INDEX IF NOT EXISTS idx_protected_links_quote_id ON protected_quote_links(quote_id);
CREATE INDEX IF NOT EXISTS idx_protected_links_creator ON protected_quote_links(created_by);
CREATE TABLE IF NOT EXISTS protected_quote_views (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 link_id TEXT NOT NULL REFERENCES protected_quote_links(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL UNIQUE,
 access_epoch INTEGER NOT NULL,
 ordinal INTEGER NOT NULL CHECK(ordinal>0),
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 FOREIGN KEY(link_id,workspace_id) REFERENCES protected_quote_links(id,workspace_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_protected_views_link ON protected_quote_views(link_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_protected_views_expiry ON protected_quote_views(expires_at,id);
CREATE INDEX IF NOT EXISTS idx_protected_views_workspace ON protected_quote_views(workspace_id,link_id);
CREATE TABLE IF NOT EXISTS protected_quote_events (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 link_id TEXT NOT NULL REFERENCES protected_quote_links(id) ON DELETE CASCADE,
 kind TEXT NOT NULL,
 actor_id TEXT REFERENCES users(id) ON DELETE SET NULL,
 detail TEXT NOT NULL DEFAULT '{}',
 created_at INTEGER NOT NULL,
 FOREIGN KEY(link_id,workspace_id) REFERENCES protected_quote_links(id,workspace_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_protected_events_link ON protected_quote_events(workspace_id,link_id,created_at DESC,id);
CREATE INDEX IF NOT EXISTS idx_protected_events_link_id ON protected_quote_events(link_id);
CREATE INDEX IF NOT EXISTS idx_protected_events_actor ON protected_quote_events(actor_id);
CREATE TABLE IF NOT EXISTS protected_quote_decisions (
 link_id TEXT PRIMARY KEY REFERENCES protected_quote_links(id) ON DELETE CASCADE,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 view_id TEXT NOT NULL,
 user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
 action TEXT NOT NULL CHECK(action IN ('approved','changes_requested','rejected')),
 comment TEXT NOT NULL DEFAULT '',
 quote_version INTEGER NOT NULL,
 snapshot_sha256 TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 FOREIGN KEY(link_id,workspace_id) REFERENCES protected_quote_links(id,workspace_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_protected_decisions_workspace ON protected_quote_decisions(workspace_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_protected_decisions_user ON protected_quote_decisions(user_id);
