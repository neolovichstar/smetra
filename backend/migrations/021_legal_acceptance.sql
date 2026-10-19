-- Explicit, versioned acceptance record. Kept separate from user content.
CREATE TABLE IF NOT EXISTS legal_acceptances (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    terms_version TEXT NOT NULL,
    disclaimer_version TEXT NOT NULL,
    accepted_at INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'first_entry',
    UNIQUE (user_id, terms_version, disclaimer_version)
);
CREATE INDEX IF NOT EXISTS idx_legal_acceptances_user_time
    ON legal_acceptances(user_id, accepted_at DESC);
