-- pg_net is infrastructure used only by the postgres-owned scheduler.
-- Its request queue briefly contains the server Authorization header.
-- Extension defaults must not grant application roles access to it or allow
-- callers to turn SQL access into arbitrary outbound HTTP requests.
-- Hosted Supabase can make these revocations no-ops: supabase_admin owns net.
-- Do not infer safety from migration success. The following signed-invocation
-- migration removes permanent credentials from the queue even in that case.
REVOKE ALL ON SCHEMA net FROM PUBLIC,anon,authenticated,smetra_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA net FROM PUBLIC,anon,authenticated,smetra_runtime;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA net FROM PUBLIC,anon,authenticated,smetra_runtime;
