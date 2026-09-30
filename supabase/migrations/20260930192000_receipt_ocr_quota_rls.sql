BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

DROP POLICY IF EXISTS smetra_runtime_assistant ON smetra.rate_limits;
CREATE POLICY smetra_runtime_assistant ON smetra.rate_limits FOR ALL TO smetra_runtime
  USING (key IN (
    encode(sha256(convert_to('assistant:month:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex'),
    encode(sha256(convert_to('receipt-ocr:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex')
  ))
  WITH CHECK (key IN (
    encode(sha256(convert_to('assistant:month:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex'),
    encode(sha256(convert_to('receipt-ocr:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex')
  ));

INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(15,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
