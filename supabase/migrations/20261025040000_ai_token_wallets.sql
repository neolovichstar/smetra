-- AI usage is metered in tokens: a non-resetting wallet plus an audit ledger.
-- Monthly allowance usage stays in rate_limits under a token-specific key.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.ai_token_wallets (
 user_id text PRIMARY KEY REFERENCES smetra.users(id) ON DELETE CASCADE,
 balance bigint NOT NULL DEFAULT 0 CHECK(balance>=0),
 updated_at bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS smetra.ai_token_ledger (
 id text PRIMARY KEY,
 user_id text NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 bucket text NOT NULL CHECK(bucket IN ('monthly','wallet')),
 delta bigint NOT NULL,
 reason text NOT NULL,
 note text NOT NULL DEFAULT '',
 ref text,
 actor_id text,
 created_at bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_token_ledger_user ON smetra.ai_token_ledger(user_id,created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_token_ledger_ref ON smetra.ai_token_ledger(user_id,ref) WHERE ref IS NOT NULL;
ALTER TABLE smetra.ai_token_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.ai_token_wallets FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.ai_token_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.ai_token_ledger FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.ai_token_wallets FROM PUBLIC, anon, authenticated;
REVOKE ALL ON smetra.ai_token_ledger FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.ai_token_wallets TO smetra_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.ai_token_ledger TO smetra_runtime;
-- Balances change only through the private server runtime role.
CREATE POLICY ai_token_wallets_runtime ON smetra.ai_token_wallets
 FOR ALL TO smetra_runtime USING(true) WITH CHECK(true);
CREATE POLICY ai_token_ledger_runtime ON smetra.ai_token_ledger
 FOR ALL TO smetra_runtime USING(true) WITH CHECK(true);
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(57,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
