CREATE TABLE IF NOT EXISTS legal_acceptances (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 terms_version TEXT NOT NULL,
 disclaimer_version TEXT NOT NULL,
 accepted_at INTEGER NOT NULL,
 source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_legal_acceptances_versions
 ON legal_acceptances(terms_version,disclaimer_version);
INSERT OR IGNORE INTO schema_migrations(version,applied_at)
VALUES(35,strftime('%s','now'));
