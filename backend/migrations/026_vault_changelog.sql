CREATE TABLE IF NOT EXISTS product_updates (
 id TEXT PRIMARY KEY,title TEXT NOT NULL,version TEXT NOT NULL DEFAULT '',
 body TEXT NOT NULL,published INTEGER NOT NULL DEFAULT 1 CHECK(published IN (0,1)),
 published_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,
 created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
 view_count INTEGER NOT NULL DEFAULT 0 CHECK(view_count>=0),
 likes INTEGER NOT NULL DEFAULT 0 CHECK(likes>=0),
 dislikes INTEGER NOT NULL DEFAULT 0 CHECK(dislikes>=0)
);
CREATE INDEX IF NOT EXISTS idx_product_updates_published ON product_updates(published,published_at DESC);
CREATE TABLE IF NOT EXISTS product_update_views (
 update_id TEXT NOT NULL REFERENCES product_updates(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 created_at INTEGER NOT NULL,PRIMARY KEY(update_id,user_id)
);
CREATE TABLE IF NOT EXISTS product_update_reactions (
 update_id TEXT NOT NULL REFERENCES product_updates(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 reaction TEXT NOT NULL CHECK(reaction IN ('like','dislike')),
 updated_at INTEGER NOT NULL,PRIMARY KEY(update_id,user_id)
);
