-- Workspace storage (archive flag and file source) and «Что нового» product updates.
-- Deployment gated on version 65. Additive only.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.files ADD COLUMN IF NOT EXISTS archived_at bigint;
ALTER TABLE smetra.files ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS smetra.changelog_posts (
 id text PRIMARY KEY,
 title text NOT NULL,
 body text NOT NULL,
 tag text NOT NULL DEFAULT '',
 author_id text REFERENCES smetra.users(id) ON DELETE SET NULL,
 published_at bigint NOT NULL,
 updated_at bigint NOT NULL,
 deleted_at bigint
);
CREATE INDEX IF NOT EXISTS idx_changelog_posts_published ON smetra.changelog_posts(published_at DESC);
CREATE TABLE IF NOT EXISTS smetra.changelog_views (
 post_id text NOT NULL REFERENCES smetra.changelog_posts(id) ON DELETE CASCADE,
 user_id text NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 viewed_at bigint NOT NULL,
 PRIMARY KEY(post_id,user_id)
);
CREATE TABLE IF NOT EXISTS smetra.changelog_reactions (
 post_id text NOT NULL REFERENCES smetra.changelog_posts(id) ON DELETE CASCADE,
 user_id text NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 reaction text NOT NULL CHECK(reaction IN ('up','love','fire','down')),
 created_at bigint NOT NULL,
 PRIMARY KEY(post_id,user_id)
);
-- Read and written only through the server connection, like the partner tables.
DO $private$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['changelog_posts','changelog_views','changelog_reactions'] LOOP
  EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC, anon, authenticated, smetra_runtime',t);
 END LOOP;
END $private$;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(65,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
