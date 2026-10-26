BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='90s';

ALTER TABLE smetra.files
 ADD COLUMN IF NOT EXISTS owner_user_id TEXT REFERENCES smetra.users(id) ON DELETE RESTRICT;
ALTER TABLE smetra.files
 ADD COLUMN IF NOT EXISTS vault_scope TEXT NOT NULL DEFAULT 'workspace';

-- Keep attachments already bound to an object or estimate shared.
-- For legacy unbound files, attribute them to the earliest recorded uploader.
-- On old installations with no matching activity, the workspace owner is the
-- only defensible fallback. Never make an unbound legacy file team-visible.
UPDATE smetra.files f
SET owner_user_id = COALESCE(
  (SELECT a.actor_id FROM smetra.activity a
   WHERE a.workspace_id=f.workspace_id AND a.entity_id=f.id
     AND a.entity_type='file' AND a.actor_id IS NOT NULL
   ORDER BY a.created_at ASC,a.id ASC LIMIT 1),
  (SELECT w.owner_id FROM smetra.workspaces w WHERE w.id=f.workspace_id)
)
WHERE f.owner_user_id IS NULL;
UPDATE smetra.files
SET vault_scope = CASE
 WHEN quote_id IS NULL AND project_id IS NULL AND client_id IS NULL
      AND construction_id IS NULL AND public=0
 THEN 'personal' ELSE 'workspace' END
WHERE vault_scope='workspace';

ALTER TABLE smetra.files
 ALTER COLUMN owner_user_id SET NOT NULL;
ALTER TABLE smetra.files
 ADD CONSTRAINT files_vault_scope_valid CHECK (
  vault_scope IN ('personal','workspace')
  AND (vault_scope<>'personal' OR (
      public=0 AND quote_id IS NULL AND project_id IS NULL
      AND client_id IS NULL AND construction_id IS NULL
  ))
 );
CREATE INDEX IF NOT EXISTS files_personal_owner_idx
 ON smetra.files(owner_user_id,created_at DESC,id DESC)
 WHERE vault_scope='personal';
CREATE INDEX IF NOT EXISTS files_team_workspace_idx
 ON smetra.files(workspace_id,created_at DESC,id DESC)
 WHERE vault_scope='workspace';

-- Effective quotas are derived server-side from ACTIVE subscription records.
-- A team membership never expands someone's personal allowance. Only plans
-- owned by this person, including historical personal Pro grants, count.
CREATE OR REPLACE FUNCTION smetra.vault_user_quota(uid TEXT)
 RETURNS BIGINT LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
 AS $quota$
 SELECT GREATEST(
   100000000::bigint,
   COALESCE((
     SELECT MAX(
       CASE
         WHEN w.entitlement_until>extract(epoch FROM now())::bigint
              AND lower(w.subscription_status) IN ('active','trialing','paid')
              AND w.plan IN ('team','pro_team','team_month','team_year','pro_plus',
              'pro_plus_month','pro_plus_year','pro_plus_monthly','pro_plus_yearly',
              'team_monthly','team_yearly') THEN 5000000000::bigint
         WHEN w.entitlement_until>extract(epoch FROM now())::bigint
              AND lower(w.subscription_status) IN ('active','trialing','paid')
              AND w.plan IN ('pro','pro_month','pro_year','pro_solo',
              'pro_solo_month','pro_solo_year','pro_solo_monthly','pro_solo_yearly')
              THEN 500000000::bigint
         ELSE 100000000::bigint
       END
     )
     FROM smetra.workspaces w WHERE w.owner_id=uid
   ),100000000::bigint),
   COALESCE((
     SELECT CASE WHEN u.entitlement_until>extract(epoch FROM now())::bigint
       THEN 500000000::bigint ELSE 100000000::bigint END
     FROM smetra.users u WHERE u.id=uid
   ),100000000::bigint)
 );
 $quota$;
REVOKE ALL ON FUNCTION smetra.vault_user_quota(TEXT) FROM PUBLIC,anon,authenticated;

CREATE OR REPLACE FUNCTION smetra.vault_workspace_quota(wid TEXT)
 RETURNS BIGINT LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
 AS $quota$
 SELECT COALESCE(
  (SELECT CASE
    WHEN w.entitlement_until>extract(epoch FROM now())::bigint
         AND lower(w.subscription_status) IN ('active','trialing','paid')
         AND w.plan IN ('team','pro_team','team_month','team_year','pro_plus',
              'pro_plus_month','pro_plus_year','pro_plus_monthly','pro_plus_yearly',
              'team_monthly','team_yearly') THEN 5000000000::bigint
    WHEN w.entitlement_until>extract(epoch FROM now())::bigint
         AND lower(w.subscription_status) IN ('active','trialing','paid')
         AND w.plan IN ('pro','pro_month','pro_year','pro_solo','pro_solo_month',
              'pro_solo_year','pro_solo_monthly','pro_solo_yearly') THEN 500000000::bigint
    WHEN u.entitlement_until>extract(epoch FROM now())::bigint
         THEN 500000000::bigint
    ELSE 100000000::bigint END
   FROM smetra.workspaces w JOIN smetra.users u ON u.id=w.owner_id
   WHERE w.id=wid),
  100000000::bigint);
 $quota$;
REVOKE ALL ON FUNCTION smetra.vault_workspace_quota(TEXT) FROM PUBLIC,anon,authenticated;

-- An authenticated user can never change a file's ownership or cross
-- workspace, even via a buggy API endpoint. Quota checks lock the billing
-- principal to serialize uploads from different devices or workspaces.
CREATE OR REPLACE FUNCTION smetra.vault_file_guard()
 RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
 AS $guard$
 DECLARE used_bytes BIGINT;
 DECLARE allowance BIGINT;
 BEGIN
   IF TG_OP='DELETE' THEN RETURN OLD; END IF;
   IF TG_OP='UPDATE' AND (
      NEW.owner_user_id IS DISTINCT FROM OLD.owner_user_id OR
      NEW.workspace_id IS DISTINCT FROM OLD.workspace_id
   ) THEN
      RAISE EXCEPTION 'File ownership or workspace cannot be reassigned'
        USING ERRCODE='23514';
   END IF;
   IF TG_OP='INSERT'
       AND NULLIF(current_setting('smetra.session_hash',true),'') IS NOT NULL
       AND NEW.owner_user_id IS DISTINCT FROM smetra.runtime_user_id() THEN
      RAISE EXCEPTION 'File owner must match authenticated user'
        USING ERRCODE='23514';
   END IF;
   IF NEW.vault_scope NOT IN ('personal','workspace') OR
      NEW.owner_user_id IS NULL THEN
       RAISE EXCEPTION 'Invalid vault owner and scope' USING ERRCODE='23514';
   END IF;
   IF NEW.vault_scope='personal' THEN
      IF NEW.public<>0 OR NEW.quote_id IS NOT NULL
         OR NEW.project_id IS NOT NULL OR NEW.client_id IS NOT NULL
         OR NEW.construction_id IS NOT NULL THEN
         RAISE EXCEPTION 'Personal file cannot be shared implicitly'
           USING ERRCODE='23514';
      END IF;
      PERFORM 1 FROM smetra.users WHERE id=NEW.owner_user_id FOR UPDATE;
      IF NOT FOUND THEN
         RAISE EXCEPTION 'Vault owner missing' USING ERRCODE='23514';
      END IF;
      SELECT COALESCE(SUM(f.size),0) INTO used_bytes
        FROM smetra.files f
        WHERE f.owner_user_id=NEW.owner_user_id
          AND f.vault_scope='personal'
          AND f.id<>NEW.id;
      allowance:=smetra.vault_user_quota(NEW.owner_user_id);
   ELSE
      PERFORM 1 FROM smetra.workspaces WHERE id=NEW.workspace_id FOR UPDATE;
      IF NOT FOUND THEN
         RAISE EXCEPTION 'Workspace missing' USING ERRCODE='23514';
      END IF;
      SELECT COALESCE(SUM(f.size),0) INTO used_bytes
        FROM smetra.files f
        WHERE f.workspace_id=NEW.workspace_id
          AND f.vault_scope='workspace'
          AND f.id<>NEW.id;
      allowance:=smetra.vault_workspace_quota(NEW.workspace_id);
   END IF;
   -- Downgrades may make a previously valid account over quota. Never block
   -- deletion or shrinking, but deny increases until space is available.
   IF TG_OP='INSERT' OR (TG_OP='UPDATE' AND
      (NEW.size>OLD.size OR NEW.vault_scope IS DISTINCT FROM OLD.vault_scope)) THEN
      IF used_bytes+NEW.size>allowance THEN
         RAISE EXCEPTION 'Storage quota exceeded' USING ERRCODE='23514';
      END IF;
   END IF;
   RETURN NEW;
 END;
 $guard$;
REVOKE ALL ON FUNCTION smetra.vault_file_guard() FROM PUBLIC,anon,authenticated;
DROP TRIGGER IF EXISTS vault_file_guard ON smetra.files;
CREATE TRIGGER vault_file_guard BEFORE INSERT OR UPDATE ON smetra.files
 FOR EACH ROW EXECUTE FUNCTION smetra.vault_file_guard();

-- RLS separates read from write: team viewers can read shared documents
-- but CANNOT modify them. Personal files stay private even inside teams.
CREATE OR REPLACE FUNCTION smetra.vault_can_edit_workspace(wid TEXT)
 RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=''
 AS $access$
 SELECT EXISTS (
  SELECT 1 FROM smetra.workspace_members m
  WHERE m.workspace_id=wid AND m.user_id=smetra.runtime_user_id()
  AND m.role IN ('owner','admin','manager','member')
 );
 $access$;
REVOKE ALL ON FUNCTION smetra.vault_can_edit_workspace(TEXT) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION smetra.vault_can_edit_workspace(TEXT) TO smetra_runtime;

DROP POLICY IF EXISTS smetra_runtime_scope ON smetra.files;
DROP POLICY IF EXISTS vault_files_read ON smetra.files;
DROP POLICY IF EXISTS vault_files_insert ON smetra.files;
DROP POLICY IF EXISTS vault_files_update ON smetra.files;
DROP POLICY IF EXISTS vault_files_delete ON smetra.files;
CREATE POLICY vault_files_read ON smetra.files FOR SELECT TO smetra_runtime
 USING (
  workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id)
  AND (vault_scope='workspace' OR owner_user_id=smetra.runtime_user_id())
 );
CREATE POLICY vault_files_insert ON smetra.files FOR INSERT TO smetra_runtime
 WITH CHECK (
  workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id)
  AND owner_user_id=smetra.runtime_user_id()
  AND (vault_scope='personal' OR smetra.vault_can_edit_workspace(workspace_id))
 );
CREATE POLICY vault_files_update ON smetra.files FOR UPDATE TO smetra_runtime
 USING (
  workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id)
  AND ( (vault_scope='personal' AND owner_user_id=smetra.runtime_user_id())
     OR (vault_scope='workspace' AND smetra.vault_can_edit_workspace(workspace_id)))
 )
 WITH CHECK (
  workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id)
  AND ( (vault_scope='personal' AND owner_user_id=smetra.runtime_user_id())
     OR (vault_scope='workspace' AND smetra.vault_can_edit_workspace(workspace_id)))
 );
CREATE POLICY vault_files_delete ON smetra.files FOR DELETE TO smetra_runtime
 USING (
  workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id)
  AND ( (vault_scope='personal' AND owner_user_id=smetra.runtime_user_id())
     OR (vault_scope='workspace' AND smetra.vault_can_edit_workspace(workspace_id)))
 );

-- Child-table policies must always resolve through the accessible parent file,
-- not a tautological workspace comparison. This also protects OCR text,
-- thumbnails and old Markdown revisions.
DROP POLICY IF EXISTS smetra_runtime_scope ON smetra.file_payloads;
CREATE POLICY smetra_runtime_scope ON smetra.file_payloads FOR ALL TO smetra_runtime
 USING (EXISTS(SELECT 1 FROM smetra.files f WHERE f.id=file_payloads.file_id))
 WITH CHECK (EXISTS(SELECT 1 FROM smetra.files f WHERE f.id=file_payloads.file_id));
DROP POLICY IF EXISTS smetra_runtime_scope ON smetra.file_text_chunks;
CREATE POLICY smetra_runtime_scope ON smetra.file_text_chunks FOR ALL TO smetra_runtime
 USING (workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id)
  AND EXISTS(SELECT 1 FROM smetra.files f
       WHERE f.id=file_text_chunks.file_id
         AND f.workspace_id=file_text_chunks.workspace_id))
 WITH CHECK (workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id)
  AND EXISTS(SELECT 1 FROM smetra.files f
       WHERE f.id=file_text_chunks.file_id
         AND f.workspace_id=file_text_chunks.workspace_id));
DROP POLICY IF EXISTS smetra_runtime_scope ON smetra.file_versions;
CREATE POLICY smetra_runtime_scope ON smetra.file_versions FOR ALL TO smetra_runtime
 USING (workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id)
  AND EXISTS(SELECT 1 FROM smetra.files f
       WHERE f.id=file_versions.file_id AND f.workspace_id=file_versions.workspace_id))
 WITH CHECK (workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id)
  AND EXISTS(SELECT 1 FROM smetra.files f
       WHERE f.id=file_versions.file_id AND f.workspace_id=file_versions.workspace_id));

INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(66,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
