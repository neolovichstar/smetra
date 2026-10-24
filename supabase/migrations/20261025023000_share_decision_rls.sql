BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
GRANT SELECT ON smetra.estimate_share_responses TO smetra_runtime;
CREATE POLICY share_responses_sender_read
 ON smetra.estimate_share_responses FOR SELECT TO smetra_runtime
 USING (
   EXISTS (
      SELECT 1 FROM smetra.estimate_shares s
      WHERE s.id=share_id
        AND s.workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
        AND smetra.runtime_workspace_allowed(s.workspace_id)
   )
 );
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(56,extract(epoch FROM now())::bigint)
 ON CONFLICT(version) DO NOTHING;
COMMIT;
