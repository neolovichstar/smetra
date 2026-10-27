BEGIN;
CREATE TABLE IF NOT EXISTS smetra.public_profiles (
 user_id TEXT PRIMARY KEY REFERENCES smetra.users(id) ON DELETE CASCADE,
 handle TEXT UNIQUE,
 display_name TEXT NOT NULL,
 headline TEXT NOT NULL DEFAULT '',
 bio TEXT NOT NULL DEFAULT '',
 city TEXT NOT NULL DEFAULT '',
 published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
 allow_messages INTEGER NOT NULL DEFAULT 1 CHECK(allow_messages IN (0,1)),
 allow_quotes INTEGER NOT NULL DEFAULT 1 CHECK(allow_quotes IN (0,1)),
 revision INTEGER NOT NULL DEFAULT 1,
 updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS smetra.profile_search_terms (
 user_id TEXT NOT NULL REFERENCES smetra.public_profiles(user_id) ON DELETE CASCADE,
 term TEXT NOT NULL,
 PRIMARY KEY(term,user_id)
);
CREATE INDEX IF NOT EXISTS idx_profile_terms_prefix ON smetra.profile_search_terms(term text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_profile_terms_user ON smetra.profile_search_terms(user_id);
CREATE INDEX IF NOT EXISTS idx_profiles_published ON smetra.public_profiles(published,updated_at DESC,user_id);
CREATE TABLE IF NOT EXISTS smetra.profile_avatars (
 user_id TEXT PRIMARY KEY REFERENCES smetra.users(id) ON DELETE CASCADE,
 content_hash TEXT NOT NULL DEFAULT '',
 content BYTEA,
 updated_at INTEGER NOT NULL
);

-- No PostgREST grants: public reads pass through the allowlisted API projection.
ALTER TABLE smetra.public_profiles ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.public_profiles FROM anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.public_profiles TO smetra_runtime;
CREATE POLICY smetra_runtime_own_profile ON smetra.public_profiles
 FOR ALL TO smetra_runtime
 USING(user_id=(SELECT smetra.runtime_user_id()))
 WITH CHECK(user_id=(SELECT smetra.runtime_user_id()));
ALTER TABLE smetra.profile_search_terms ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.profile_search_terms FROM anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.profile_search_terms TO smetra_runtime;
CREATE POLICY smetra_runtime_own_profile ON smetra.profile_search_terms
 FOR ALL TO smetra_runtime
 USING(user_id=(SELECT smetra.runtime_user_id()))
 WITH CHECK(user_id=(SELECT smetra.runtime_user_id()));
ALTER TABLE smetra.profile_avatars ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.profile_avatars FROM anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.profile_avatars TO smetra_runtime;
CREATE POLICY smetra_runtime_own_profile ON smetra.profile_avatars
 FOR ALL TO smetra_runtime
 USING(user_id=(SELECT smetra.runtime_user_id()))
 WITH CHECK(user_id=(SELECT smetra.runtime_user_id()));
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(67,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
