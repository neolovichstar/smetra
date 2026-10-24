BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
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
