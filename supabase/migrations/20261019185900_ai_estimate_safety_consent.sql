BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE IF NOT EXISTS smetra.legal_acceptances (
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 document_version TEXT NOT NULL,
 accepted_at BIGINT NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('registration','first_estimate')),
 UNIQUE(user_id,document_version)
);
CREATE INDEX IF NOT EXISTS idx_legal_acceptances_user_version
 ON smetra.legal_acceptances(user_id,document_version);

ALTER TABLE smetra.legal_acceptances ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.legal_acceptances FORCE ROW LEVEL SECURITY;
GRANT SELECT,INSERT ON smetra.legal_acceptances TO smetra_runtime;
REVOKE ALL ON smetra.legal_acceptances FROM PUBLIC,anon,authenticated;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname='smetra'
      AND tablename='legal_acceptances'
      AND policyname='smetra_runtime_legal_acceptances'
  ) THEN
    CREATE POLICY smetra_runtime_legal_acceptances
      ON smetra.legal_acceptances
      FOR ALL TO smetra_runtime
      USING (user_id=(SELECT smetra.runtime_user_id()))
      WITH CHECK (user_id=(SELECT smetra.runtime_user_id()));
  END IF;
END $$;

INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(35,extract(epoch FROM now())::BIGINT) ON CONFLICT DO NOTHING;
COMMIT;
