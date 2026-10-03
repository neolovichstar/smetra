SET lock_timeout='5s';
ALTER TABLE smetra.files ADD COLUMN index_method TEXT NOT NULL DEFAULT 'text' CHECK(index_method IN ('text','ocr'));
ALTER TABLE smetra.assistant_jobs DROP CONSTRAINT assistant_jobs_kind_check;
ALTER TABLE smetra.assistant_jobs ADD CONSTRAINT assistant_jobs_kind_check CHECK(kind IN ('chat','file_index','receipt_ocr','file_ocr'));
CREATE INDEX IF NOT EXISTS assistant_jobs_scan_source ON smetra.assistant_jobs(workspace_id,user_id,file_id,source_sha256,created_at DESC) WHERE kind='file_ocr';
DROP POLICY smetra_runtime_assistant ON smetra.rate_limits;
CREATE POLICY smetra_runtime_assistant ON smetra.rate_limits FOR ALL TO smetra_runtime
USING (key IN (
 encode(sha256(convert_to('assistant:month:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex'),
 encode(sha256(convert_to('receipt-ocr:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex'),
 encode(sha256(convert_to('file-ocr:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex')
))
WITH CHECK (key IN (
 encode(sha256(convert_to('assistant:month:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex'),
 encode(sha256(convert_to('receipt-ocr:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex'),
 encode(sha256(convert_to('file-ocr:' || to_char(now() AT TIME ZONE 'UTC','YYYY-MM') || ':' || smetra.runtime_user_id(),'UTF8')),'hex')
));
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(26,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
