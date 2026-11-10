-- Version 73. Reuse tenant-scoped quotes and templates, with their existing RLS.
-- Additive: old deployments ignore the columns; no document or token is rewritten.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT '{}';
ALTER TABLE smetra.estimate_templates ADD COLUMN IF NOT EXISTS template_kind TEXT NOT NULL DEFAULT 'quote';
CREATE INDEX IF NOT EXISTS idx_estimate_templates_kind ON smetra.estimate_templates(workspace_id,template_kind,created_at DESC);
ALTER TABLE smetra.construction_changes ADD COLUMN IF NOT EXISTS protected_quote_id TEXT;
ALTER TABLE smetra.construction_changes ADD COLUMN IF NOT EXISTS internal_cost BIGINT NOT NULL DEFAULT 0;
ALTER TABLE smetra.construction_changes ADD COLUMN IF NOT EXISTS budget_applied_at BIGINT;
ALTER TABLE smetra.construction_changes ADD COLUMN IF NOT EXISTS calculation_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE smetra.construction_changes ADD CONSTRAINT construction_changes_protected_quote_fk FOREIGN KEY(protected_quote_id,workspace_id) REFERENCES smetra.quotes(id,workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_changes_protected_quote ON smetra.construction_changes(protected_quote_id) WHERE protected_quote_id IS NOT NULL;
ALTER TABLE smetra.projects ADD COLUMN IF NOT EXISTS cost_forecast TEXT NOT NULL DEFAULT '{}';
ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS alternative_root_id TEXT;
ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS alternative_label TEXT NOT NULL DEFAULT '';
ALTER TABLE smetra.quotes ADD CONSTRAINT quote_alternative_root_fk FOREIGN KEY(alternative_root_id,workspace_id) REFERENCES smetra.quotes(id,workspace_id);
CREATE INDEX IF NOT EXISTS idx_quotes_alternatives ON smetra.quotes(workspace_id,alternative_root_id,approval_state);
CREATE UNIQUE INDEX IF NOT EXISTS idx_quote_alternative_selection ON smetra.quotes(workspace_id,alternative_root_id) WHERE alternative_root_id IS NOT NULL AND approval_state='approved';
ALTER TABLE smetra.construction_quantities ADD COLUMN IF NOT EXISTS actual_cost_data TEXT NOT NULL DEFAULT '{}';
ALTER TABLE smetra.catalog_items ADD COLUMN IF NOT EXISTS actual_rate_source TEXT NOT NULL DEFAULT '';
-- A runtime role can check legacy personal Pro eligibility without reading
-- payment/refund rows. Foreign scopes get a constant fail-closed answer.
CREATE OR REPLACE FUNCTION smetra.runtime_workspace_has_bound_payment(target_workspace TEXT)
RETURNS BOOLEAN LANGUAGE SQL STABLE SECURITY DEFINER SET search_path=''
AS $$
 SELECT CASE WHEN target_workspace=nullif(current_setting('smetra.workspace_id',true),'')
                  AND smetra.runtime_workspace_allowed(target_workspace)
 THEN EXISTS (
   SELECT 1 FROM smetra.workspaces w JOIN smetra.billing_intents b ON b.user_id=w.owner_id
   JOIN smetra.payments p ON p.id=b.payment_id
   WHERE w.id=target_workspace AND b.workspace_id IS NOT NULL AND p.status='succeeded'
     AND NOT EXISTS(SELECT 1 FROM smetra.refunds r WHERE r.payment_id=p.id AND r.status='succeeded')
 ) ELSE TRUE END
$$;
REVOKE ALL ON FUNCTION smetra.runtime_workspace_has_bound_payment(TEXT) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION smetra.runtime_workspace_has_bound_payment(TEXT) TO smetra_runtime;
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(73,extract(epoch from now())::BIGINT) ON CONFLICT DO NOTHING;
COMMIT;
