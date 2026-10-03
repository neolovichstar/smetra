SET lock_timeout='5s';
ALTER TABLE smetra.assistant_jobs DROP CONSTRAINT assistant_jobs_kind_check;
ALTER TABLE smetra.assistant_jobs ADD CONSTRAINT assistant_jobs_kind_check CHECK(kind IN ('chat','file_index','receipt_ocr'));
CREATE INDEX IF NOT EXISTS assistant_jobs_receipt_source ON smetra.assistant_jobs(workspace_id,user_id,file_id,source_sha256,created_at DESC) WHERE kind='receipt_ocr';
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(25,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
