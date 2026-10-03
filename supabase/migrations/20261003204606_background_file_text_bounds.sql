BEGIN;
SET LOCAL lock_timeout='5s';
ALTER TABLE smetra.file_text_chunks DROP CONSTRAINT file_text_chunks_text_check;
ALTER TABLE smetra.file_text_chunks ADD CONSTRAINT file_text_chunks_text_check CHECK(length(text)<=120000);
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(24,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
