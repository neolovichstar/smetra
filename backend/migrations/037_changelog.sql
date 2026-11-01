-- «Что нового»: product updates in Markdown, one view and one reaction per person per post.
CREATE TABLE IF NOT EXISTS changelog_posts (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tag TEXT NOT NULL DEFAULT '',
  author_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  published_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  deleted_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_changelog_posts_published ON changelog_posts(published_at DESC);
CREATE TABLE IF NOT EXISTS changelog_views (
  post_id TEXT NOT NULL REFERENCES changelog_posts(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  viewed_at INTEGER NOT NULL,
  PRIMARY KEY(post_id, user_id)
);
CREATE TABLE IF NOT EXISTS changelog_reactions (
  post_id TEXT NOT NULL REFERENCES changelog_posts(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reaction TEXT NOT NULL CHECK(reaction IN ('up','love','fire','down')),
  created_at INTEGER NOT NULL,
  PRIMARY KEY(post_id, user_id)
);
