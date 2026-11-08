BEGIN;
-- Manual uploads and deliberate deletions stay authoritative when OAuth is linked.
ALTER TABLE smetra.profile_avatars
 ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(70,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
