# RuStore Push

The app-side SDK integration and backend delivery queue are ready for review. Delivery stays disabled until both server variables are configured:

- `RUSTORE_PUSH_PROJECT_ID`: ID from the existing app's RuStore Console > Push notifications > Projects.
- `RUSTORE_PUSH_SERVICE_TOKEN`: server-only service token from that project. Never put it in Android BuildConfig or a client file.

The worker reuses the existing `ASSISTANT_WORKER_SECRET` and Supabase Vault secret `smetra_assistant_worker_secret`. Its Supabase `pg_cron` job signs short-lived, one-use requests to `GET /api/cron/push`; it does not place a persistent bearer token into the `pg_net` request queue. The scheduler is added by `supabase/migrations/20261018213000_push_worker_scheduler.sql`.

## Deploy steps

1. Review and merge this branch after CI is green.
2. Back up the existing Supabase production database.
3. Apply `supabase/migrations/20261018193000_rustore_push_notifications.sql`, then `supabase/migrations/20261018210000_query_performance_indexes.sql`, then `supabase/migrations/20261018213000_push_worker_scheduler.sql`, to the existing Supabase project. The first adds push-specific tables and per-device delivery tracking without recreating or changing `file_versions`; the second adds indexes for common workspace relationships; the third registers the signed, one-minute worker in the existing Supabase `pg_cron` scheduler. The local SQLite startup applies `backend/migrations/022_push_notifications.sql` and `backend/migrations/023_query_performance_indexes.sql`.
4. Configure `RUSTORE_PUSH_PROJECT_ID` and server-only `RUSTORE_PUSH_SERVICE_TOKEN` in the existing Vercel production environment. Keep the already configured `ASSISTANT_WORKER_SECRET` matched to the existing Supabase Vault secret; do not create a second worker secret.
5. In RuStore Console, create a Push project for the existing application ID `ru.smetra.mobile`; match the SHA-256 certificate fingerprint of the signed release APK. Use the project ID as `-PrustorePushProjectId=...` or `RUSTORE_PUSH_PROJECT_ID=...` at Android build time.
6. Build and test a signed Android APK/AAB in CI, then upload it to the existing RuStore app listing. No keystore or production secret is included in the repository.

The app asks for Android 13+ notification permission only when the user enables pushes. The backend binds each registration to the current session; push text intentionally excludes client names, comments and amounts. After enabling provider credentials and the scheduler, perform an end-to-end test on a device with the RuStore distributor installed.

## Operational behavior

The queue is transactional with in-app notifications, tracks each recipient separately to prevent duplicate delivery after partial failure, claims work with short leases, sends to a bounded number of devices in parallel, and retries transient provider failures with backoff. If credentials are temporarily absent, due events are deferred for one hour instead of waking the worker every minute. Daily maintenance removes registrations tied to expired sessions and purges completed outbox history after 30 days. No new push is queued when RuStore provider credentials are absent.
