-- Fix runtime token metering after migrating from request quotas.
-- The existing rate_limits RLS policy still permits assistant:month:, file-ocr:
-- and receipt-ocr: but not the current assistant:tokens: key.
-- Add one narrowly-scoped permissive policy; do not broaden the old policy.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE POLICY smetra_runtime_assistant_tokens ON smetra.rate_limits
  AS PERMISSIVE FOR ALL TO smetra_runtime
  USING (key = encode(sha256(convert_to(
    'assistant:tokens:' || to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM')
      || ':' || (SELECT smetra.runtime_user_id()), 'UTF8'
  )), 'hex'))
  WITH CHECK (key = encode(sha256(convert_to(
    'assistant:tokens:' || to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM')
      || ':' || (SELECT smetra.runtime_user_id()), 'UTF8'
  )), 'hex'));

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (58, extract(epoch FROM now())::bigint)
ON CONFLICT (version) DO NOTHING;
COMMIT;
