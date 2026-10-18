# RuStore Push

The app-side SDK integration and backend delivery queue are ready for review. Delivery stays disabled until both server variables are configured:

- `RUSTORE_PUSH_PROJECT_ID`: ID from the existing app's RuStore Console > Push notifications > Projects.
- `RUSTORE_PUSH_SERVICE_TOKEN`: server-only service token from that project. Never put it in Android BuildConfig or a client file.

The worker also requires `CRON_SECRET` (at least 32 characters) or `PUSH_WORKER_SECRET`. A scheduler must call `GET /api/cron/push` with `Authorization: Bearer <secret>`. Reuse the existing scheduling infrastructure; the current Supabase project already has `pg_cron` jobs, while the Vercel Hobby plan does not support frequent Vercel Cron schedules. Do not create another Vercel/Supabase project just for pushes.

## Deploy steps

1. Review and merge this branch after CI is green.
2. Back up the existing Supabase production database.
3. Apply `supabase/migrations/20261018193000_rustore_push_notifications.sql`, then `supabase/migrations/20261018210000_query_performance_indexes.sql`, to the existing Supabase project. The first adds push-specific tables and delivery tracking without recreating or changing `file_versions`; the second adds indexes for common workspace relationships. The local SQLite startup applies `backend/migrations/022_push_notifications.sql` and `backend/migrations/023_query_performance_indexes.sql`.
4. Configure the three server environment variables in the existing production environment.
5. In RuStore Console, create a Push project for the existing application ID `ru.smetra.mobile`; match the SHA-256 certificate fingerprint of the signed release APK. Use the project ID as `-PrustorePushProjectId=...` or `RUSTORE_PUSH_PROJECT_ID=...` at Android build time.
6. Build and test a signed Android APK/AAB in CI, then upload it to the existing RuStore app listing. No keystore or production secret is included in the repository.

The app asks for Android 13+ notification permission only when the user enables pushes. The backend binds each registration to the current session; push text intentionally excludes client names, comments and amounts. After enabling provider credentials and the scheduler, perform an end-to-end test on a device with the RuStore distributor installed.

## Operational behavior

The queue is transactional with in-app notifications, claims events with a short lease, sends to a bounded number of devices in parallel, retries transient provider failures with backoff, and removes expired provider tokens. No push is queued when RuStore provider credentials are absent.
