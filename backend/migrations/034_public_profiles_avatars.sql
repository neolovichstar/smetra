CREATE TABLE IF NOT EXISTS public_profiles (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
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
CREATE TABLE IF NOT EXISTS profile_search_terms (
 user_id TEXT NOT NULL REFERENCES public_profiles(user_id) ON DELETE CASCADE,
 term TEXT NOT NULL,
 PRIMARY KEY(term,user_id)
);
CREATE INDEX IF NOT EXISTS idx_profile_terms_user ON profile_search_terms(user_id);
CREATE INDEX IF NOT EXISTS idx_profiles_published ON public_profiles(published,updated_at DESC,user_id);
CREATE TABLE IF NOT EXISTS profile_avatars (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 content_hash TEXT NOT NULL DEFAULT '',
 content BLOB,
 updated_at INTEGER NOT NULL
);
