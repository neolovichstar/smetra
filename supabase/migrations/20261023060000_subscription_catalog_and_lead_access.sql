-- Subscription catalogue v2 and included marketplace lead access.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

ALTER TABLE smetra.billing_subscriptions
  DROP CONSTRAINT IF EXISTS billing_subscriptions_product_code_check;
ALTER TABLE smetra.billing_subscriptions
  ADD CONSTRAINT billing_subscriptions_product_code_check
  CHECK (product_code IN (
    'pro_solo_month','pro_solo_year','pro_plus_month',
    'pro_team_month','pro_team_year','smart_supplier_month'
  ));
ALTER TABLE smetra.billing_subscriptions
  DROP CONSTRAINT IF EXISTS billing_subscriptions_check;
ALTER TABLE smetra.billing_subscriptions
  DROP CONSTRAINT IF EXISTS billing_subscriptions_workspace_plan_check;
ALTER TABLE smetra.billing_subscriptions
  ADD CONSTRAINT billing_subscriptions_workspace_plan_check
  CHECK (
    (product_code IN ('pro_team_month','pro_team_year') AND workspace_id IS NOT NULL)
    OR
    (product_code NOT IN ('pro_team_month','pro_team_year') AND workspace_id IS NULL)
  );

CREATE TABLE IF NOT EXISTS smetra.lead_access_grants (
  id TEXT PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES smetra.marketplace_leads(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
  workspace_id TEXT REFERENCES smetra.workspaces(id) ON DELETE SET NULL,
  idempotency_key TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  UNIQUE(lead_id,user_id),
  UNIQUE(user_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_lead_access_grants_user_time
  ON smetra.lead_access_grants(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_access_grants_workspace_time
  ON smetra.lead_access_grants(workspace_id,created_at DESC)
  WHERE workspace_id IS NOT NULL;

INSERT INTO smetra.lead_access_grants(id,lead_id,user_id,workspace_id,idempotency_key,created_at)
SELECT p.id,p.lead_id,p.buyer_user_id,p.buyer_workspace_id,'legacy:' || p.id,p.purchased_at
FROM smetra.lead_purchases p
ON CONFLICT DO NOTHING;

ALTER TABLE smetra.lead_access_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.lead_access_grants FORCE ROW LEVEL SECURITY;
GRANT SELECT,INSERT ON smetra.lead_access_grants TO smetra_runtime;
DO $policies$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname='smetra' AND tablename='lead_access_grants'
      AND policyname='smetra_runtime_lead_access_grants'
  ) THEN
    CREATE POLICY smetra_runtime_lead_access_grants
      ON smetra.lead_access_grants FOR ALL TO smetra_runtime
      USING (
        user_id=(SELECT smetra.runtime_user_id())
        OR (
          workspace_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM smetra.workspace_members m
            WHERE m.workspace_id=lead_access_grants.workspace_id
              AND m.user_id=(SELECT smetra.runtime_user_id())
          )
        )
      )
      WITH CHECK (
        user_id=(SELECT smetra.runtime_user_id())
        AND (
          workspace_id IS NULL OR EXISTS (
            SELECT 1 FROM smetra.workspace_members m
            WHERE m.workspace_id=lead_access_grants.workspace_id
              AND m.user_id=(SELECT smetra.runtime_user_id())
          )
        )
      );
  END IF;
END
$policies$;

UPDATE smetra.workspaces SET seat_limit=5 WHERE plan='pro_team' AND seat_limit>5;
INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(48,EXTRACT(EPOCH FROM NOW())::BIGINT)
ON CONFLICT(version) DO NOTHING;
COMMIT;
