-- Record explicit acceptance of the current terms and AI estimate disclaimer.
-- This table is private: runtime users can read/insert only their own records.
BEGIN;
CREATE TABLE IF NOT EXISTS smetra.legal_acceptances (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
    terms_version TEXT NOT NULL,
    disclaimer_version TEXT NOT NULL,
    accepted_at BIGINT NOT NULL,
    source TEXT NOT NULL DEFAULT 'first_entry',
    UNIQUE (user_id, terms_version, disclaimer_version)
);
CREATE INDEX IF NOT EXISTS idx_legal_acceptances_user_time
    ON smetra.legal_acceptances(user_id, accepted_at DESC);
ALTER TABLE smetra.legal_acceptances ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.legal_acceptances FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS smetra_runtime_legal_acceptance ON smetra.legal_acceptances;
CREATE POLICY smetra_runtime_legal_acceptance
    ON smetra.legal_acceptances
    FOR ALL TO smetra_runtime
    USING (user_id = smetra.runtime_user_id())
    WITH CHECK (user_id = smetra.runtime_user_id());
GRANT SELECT, INSERT ON smetra.legal_acceptances TO smetra_runtime;
COMMIT;
