BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE smetra.pricing_assignments (
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE, experiment TEXT NOT NULL,
 variant TEXT NOT NULL, created_at BIGINT NOT NULL, PRIMARY KEY(user_id,experiment)
);
CREATE TABLE smetra.growth_events (
 id TEXT PRIMARY KEY, user_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 name TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', variant TEXT NOT NULL DEFAULT '',
 dedupe_key TEXT NOT NULL UNIQUE, created_at BIGINT NOT NULL
);
CREATE INDEX idx_growth_user ON smetra.growth_events(user_id,name,created_at);
CREATE INDEX idx_growth_name ON smetra.growth_events(name,created_at);
CREATE TABLE smetra.billing_intents (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES smetra.users(id), request_key TEXT NOT NULL,
 plan TEXT NOT NULL, amount_kopecks BIGINT NOT NULL CHECK(amount_kopecks>0),
 duration_days BIGINT NOT NULL CHECK(duration_days>0), variant TEXT NOT NULL, source TEXT NOT NULL,
 is_test BIGINT NOT NULL CHECK(is_test IN (0,1)), payment_id TEXT UNIQUE REFERENCES smetra.payments(id),
 created_at BIGINT NOT NULL, UNIQUE(user_id,request_key)
);
CREATE INDEX idx_billing_intents_time ON smetra.billing_intents(is_test,created_at);
CREATE TABLE smetra.referral_links (
 user_id TEXT PRIMARY KEY REFERENCES smetra.users(id) ON DELETE CASCADE, code TEXT NOT NULL UNIQUE, created_at BIGINT NOT NULL
);
CREATE TABLE smetra.referral_rewards (
 invitee_id TEXT PRIMARY KEY REFERENCES smetra.users(id) ON DELETE CASCADE,
 inviter_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 bonus BIGINT NOT NULL CHECK(bonus>0), period TEXT NOT NULL, rewarded_at BIGINT
);

DO $migration$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['growth_events','pricing_assignments','billing_intents','referral_links','referral_rewards'] LOOP
  EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.%I TO smetra_runtime',t);
  EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC,anon,authenticated',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['growth_events','pricing_assignments','billing_intents','referral_links'] LOOP
  EXECUTE format('CREATE POLICY runtime_growth ON smetra.%I FOR ALL TO smetra_runtime USING (user_id=smetra.runtime_user_id()) WITH CHECK (user_id=smetra.runtime_user_id())',t);
 END LOOP;
END $migration$;
REVOKE INSERT,UPDATE,DELETE ON smetra.billing_intents,smetra.referral_links FROM smetra_runtime;
REVOKE INSERT,UPDATE,DELETE ON smetra.referral_rewards FROM smetra_runtime;
GRANT UPDATE(rewarded_at,period) ON smetra.referral_rewards TO smetra_runtime;
CREATE POLICY runtime_referral_read ON smetra.referral_rewards FOR SELECT TO smetra_runtime USING (inviter_id=smetra.runtime_user_id() OR invitee_id=smetra.runtime_user_id());
CREATE POLICY runtime_referral_activate ON smetra.referral_rewards FOR UPDATE TO smetra_runtime USING (invitee_id=smetra.runtime_user_id()) WITH CHECK (invitee_id=smetra.runtime_user_id());
CREATE POLICY runtime_referral_insert ON smetra.referral_rewards FOR INSERT TO smetra_runtime WITH CHECK (invitee_id=smetra.runtime_user_id());
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(28,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
