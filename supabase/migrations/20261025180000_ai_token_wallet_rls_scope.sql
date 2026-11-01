-- Token wallets and their ledger were readable and writable for every user
-- through the runtime role (USING true). Every runtime operation acts for the
-- session's own user (charges, ad rewards, balance); payments and admin
-- adjustments run on the server connection, which RLS does not restrict.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
DROP POLICY IF EXISTS ai_token_wallets_runtime ON smetra.ai_token_wallets;
DROP POLICY IF EXISTS ai_token_ledger_runtime ON smetra.ai_token_ledger;
CREATE POLICY ai_token_wallets_runtime ON smetra.ai_token_wallets
  FOR ALL TO smetra_runtime
  USING (user_id = (SELECT smetra.runtime_user_id()))
  WITH CHECK (user_id = (SELECT smetra.runtime_user_id()));
CREATE POLICY ai_token_ledger_runtime ON smetra.ai_token_ledger
  FOR ALL TO smetra_runtime
  USING (user_id = (SELECT smetra.runtime_user_id()))
  WITH CHECK (user_id = (SELECT smetra.runtime_user_id()));
INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (60, extract(epoch FROM now())::bigint)
ON CONFLICT (version) DO NOTHING;
COMMIT;
