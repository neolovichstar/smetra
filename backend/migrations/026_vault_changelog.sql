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

CREATE TRIGGER IF NOT EXISTS trg_product_view_add AFTER INSERT ON product_update_views BEGIN
 UPDATE product_updates SET view_count=view_count+1 WHERE id=NEW.update_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_product_view_remove AFTER DELETE ON product_update_views BEGIN
 UPDATE product_updates SET view_count=view_count-1 WHERE id=OLD.update_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_product_react_add AFTER INSERT ON product_update_reactions BEGIN
 UPDATE product_updates SET likes=likes+CASE WHEN NEW.reaction='like' THEN 1 ELSE 0 END,
 dislikes=dislikes+CASE WHEN NEW.reaction='dislike' THEN 1 ELSE 0 END WHERE id=NEW.update_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_product_react_change AFTER UPDATE ON product_update_reactions BEGIN
 UPDATE product_updates SET likes=likes-CASE WHEN OLD.reaction='like' THEN 1 ELSE 0 END+CASE WHEN NEW.reaction='like' THEN 1 ELSE 0 END,
 dislikes=dislikes-CASE WHEN OLD.reaction='dislike' THEN 1 ELSE 0 END+CASE WHEN NEW.reaction='dislike' THEN 1 ELSE 0 END WHERE id=NEW.update_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_product_react_remove AFTER DELETE ON product_update_reactions BEGIN
 UPDATE product_updates SET likes=likes-CASE WHEN OLD.reaction='like' THEN 1 ELSE 0 END,
 dislikes=dislikes-CASE WHEN OLD.reaction='dislike' THEN 1 ELSE 0 END WHERE id=OLD.update_id;
END;
