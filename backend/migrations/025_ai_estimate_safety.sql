-- Record explicit acceptance of the AI-estimate terms for the exact document version.
CREATE TABLE IF NOT EXISTS legal_acceptances (
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 document_version TEXT NOT NULL,
 accepted_at INTEGER NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('registration','first_estimate')),
 UNIQUE(user_id,document_version)
);
CREATE INDEX IF NOT EXISTS idx_legal_acceptances_user_version
 ON legal_acceptances(user_id,document_version);

INSERT OR IGNORE INTO schema_migrations(version,applied_at)
VALUES(35,strftime('%s','now'));
