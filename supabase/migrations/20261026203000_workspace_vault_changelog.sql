BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.files ADD COLUMN IF NOT EXISTS archived BIGINT NOT NULL DEFAULT 0 CHECK(archived IN (0,1));
CREATE INDEX IF NOT EXISTS idx_files_workspace_archived ON smetra.files(workspace_id,archived,created_at DESC);

CREATE TABLE IF NOT EXISTS smetra.product_updates (
 id TEXT PRIMARY KEY,title TEXT NOT NULL,version TEXT NOT NULL DEFAULT '',
 body TEXT NOT NULL,published BIGINT NOT NULL DEFAULT 1 CHECK(published IN (0,1)),
 published_at BIGINT NOT NULL,updated_at BIGINT NOT NULL,
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 view_count BIGINT NOT NULL DEFAULT 0 CHECK(view_count>=0),
 likes BIGINT NOT NULL DEFAULT 0 CHECK(likes>=0),
 dislikes BIGINT NOT NULL DEFAULT 0 CHECK(dislikes>=0)
);
CREATE INDEX IF NOT EXISTS idx_product_updates_published ON smetra.product_updates(published,published_at DESC);
CREATE TABLE IF NOT EXISTS smetra.product_update_views (
 update_id TEXT NOT NULL REFERENCES smetra.product_updates(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 created_at BIGINT NOT NULL,PRIMARY KEY(update_id,user_id)
);
CREATE TABLE IF NOT EXISTS smetra.product_update_reactions (
 update_id TEXT NOT NULL REFERENCES smetra.product_updates(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 reaction TEXT NOT NULL CHECK(reaction IN ('like','dislike')),
 updated_at BIGINT NOT NULL,PRIMARY KEY(update_id,user_id)
);
CREATE OR REPLACE FUNCTION smetra.runtime_is_admin() RETURNS BOOLEAN
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
 AS $$
 SELECT EXISTS (
   SELECT 1 FROM smetra.users u
   WHERE u.id=smetra.runtime_user_id() AND u.role='admin'
 )
 $$;
REVOKE ALL ON FUNCTION smetra.runtime_is_admin() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION smetra.runtime_is_admin() TO smetra_runtime;

GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.product_updates TO smetra_runtime;
GRANT SELECT,INSERT,DELETE ON smetra.product_update_views TO smetra_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.product_update_reactions TO smetra_runtime;

ALTER TABLE smetra.product_updates ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.product_updates FORCE ROW LEVEL SECURITY;
CREATE POLICY product_updates_read ON smetra.product_updates FOR SELECT TO smetra_runtime
 USING (smetra.runtime_user_id() IS NOT NULL AND (published=1 OR smetra.runtime_is_admin()));
CREATE POLICY product_updates_write ON smetra.product_updates FOR ALL TO smetra_runtime
 USING (smetra.runtime_is_admin()) WITH CHECK (smetra.runtime_is_admin());

ALTER TABLE smetra.product_update_views ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.product_update_views FORCE ROW LEVEL SECURITY;
CREATE POLICY product_update_views_owner ON smetra.product_update_views FOR ALL TO smetra_runtime
 USING (user_id=smetra.runtime_user_id()) WITH CHECK (user_id=smetra.runtime_user_id());

ALTER TABLE smetra.product_update_reactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.product_update_reactions FORCE ROW LEVEL SECURITY;
CREATE POLICY product_update_reactions_owner ON smetra.product_update_reactions FOR ALL TO smetra_runtime
 USING (user_id=smetra.runtime_user_id()) WITH CHECK (user_id=smetra.runtime_user_id());

REVOKE ALL ON smetra.product_updates,smetra.product_update_views,smetra.product_update_reactions
 FROM PUBLIC,anon,authenticated;


-- Trigger-owned counters: members never need UPDATE permissions on the public announcement row.
CREATE OR REPLACE FUNCTION smetra.product_update_count_trigger() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
 AS $
 BEGIN
  IF TG_TABLE_NAME='product_update_views' THEN
    IF TG_OP='INSERT' THEN
      UPDATE smetra.product_updates SET view_count=view_count+1 WHERE id=NEW.update_id;
    ELSE
      UPDATE smetra.product_updates SET view_count=view_count-1 WHERE id=OLD.update_id;
    END IF;
  ELSE
    IF TG_OP IN ('UPDATE','DELETE') THEN
      UPDATE smetra.product_updates SET
        likes=likes-CASE WHEN OLD.reaction='like' THEN 1 ELSE 0 END,
        dislikes=dislikes-CASE WHEN OLD.reaction='dislike' THEN 1 ELSE 0 END
      WHERE id=OLD.update_id;
    END IF;
    IF TG_OP IN ('INSERT','UPDATE') THEN
      UPDATE smetra.product_updates SET
        likes=likes+CASE WHEN NEW.reaction='like' THEN 1 ELSE 0 END,
        dislikes=dislikes+CASE WHEN NEW.reaction='dislike' THEN 1 ELSE 0 END
      WHERE id=NEW.update_id;
    END IF;
  END IF;
  RETURN NULL;
 END;
 $;
REVOKE ALL ON FUNCTION smetra.product_update_count_trigger() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER product_update_view_insert AFTER INSERT ON smetra.product_update_views
 FOR EACH ROW EXECUTE FUNCTION smetra.product_update_count_trigger();
CREATE TRIGGER product_update_view_delete AFTER DELETE ON smetra.product_update_views
 FOR EACH ROW EXECUTE FUNCTION smetra.product_update_count_trigger();
CREATE TRIGGER product_update_reaction_insert AFTER INSERT ON smetra.product_update_reactions
 FOR EACH ROW EXECUTE FUNCTION smetra.product_update_count_trigger();
CREATE TRIGGER product_update_reaction_update AFTER UPDATE ON smetra.product_update_reactions
 FOR EACH ROW EXECUTE FUNCTION smetra.product_update_count_trigger();
CREATE TRIGGER product_update_reaction_delete AFTER DELETE ON smetra.product_update_reactions
 FOR EACH ROW EXECUTE FUNCTION smetra.product_update_count_trigger();

INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(40,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
