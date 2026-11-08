# Production audit — 2026-10-18

## Changes made

- Restored `backend/migrations/012_file_versions.sql`, which was referenced during SQLite startup but absent from the uploaded project. The PostgreSQL migration also restores this table for existing cloud deployments.
- Added versioned migration 30 for RuStore push registration and a transactional outbox. Push delivery is disabled safely until the project ID and server token are configured.
- Added account/session-bound Android installation registration and best-effort unregistration on opt-out, logout, and account deletion. A device is eligible for delivery only while its bound backend session remains valid.
- Added retry/backoff and bounded concurrent RuStore sends so unreachable devices do not make every request wait sequentially. Notification text on the lock screen is generic by design.
- Added a notification center and push controls in Android settings, plus the Android 13+ runtime permission request.
- Android now consumes the same backend-driven presentation fields and brand accent instead of substituting a different blue. Bumped mobile version to `1.7.25` / version code `37`.
- Reduced avoidable SQLite connection setup work by avoiding repeated WAL-mode writes, and added indexes for common workspace membership, task due-date, payment history, push registration, and push queue access.
- Cleaned a compile-time Java variable-order issue in the notification center and removed a duplicate SQLite index declaration.

## Validation performed

- `python -m compileall -q backend api` — PASS.
- `python -m unittest discover -s tests -v` — PASS (8 push tests, including retry/backoff and expired-token cleanup).
- Fresh SQLite initialization/migration — PASS; schema migration version 30 and required tables/indexes verified.
- `python scripts/build_web.py` — PASS (112 web files generated).
- Android Manifest XML parse — PASS.
- `apps/mobile/gradlew assembleDebug` — NOT VERIFIED: the Gradle 8.9 distribution is not cached and this environment cannot resolve `services.gradle.org`. Run the Android build in CI or a network-enabled developer environment before publishing.

## Release prerequisites — not performed automatically

1. Rotate production secrets that were present in the supplied local environment files. Those local files are intentionally excluded from the cleaned archive; start from `.env.example` and provision real values in your secret manager.
2. Create/configure a RuStore Push project for application ID `ru.smetra.mobile` and the exact release signing certificate. Debug and release signatures may require separate RuStore projects.
3. Set `RUSTORE_PUSH_PROJECT_ID` for the Android Gradle build. Set `RUSTORE_PUSH_PROJECT_ID` and `RUSTORE_PUSH_SERVICE_TOKEN` in the production backend environment. Keep the service token server-side only.
4. Reuse the existing `CRON_SECRET` used by other cron routes (or coordinate any rotation with all cron jobs). Configure a protected scheduler to call `GET /api/cron/push` approximately once per minute with `Authorization: Bearer $CRON_SECRET`.
5. Back up the production database and apply `supabase/migrations/20261018193000_rustore_push_notifications.sql` before deploying the backend. SQLite development deployments apply migration 30 automatically.
6. Build and test a signed release with the actual RuStore project/signature, Android 13+ notification permission, a real account and a real push event. Deploying, publishing to RuStore or changing the production database was not done as part of this archive-only pass.

The public website URL could not be fetched from this environment, so the interface consistency check used the repository's shared `/api/mobile/presentation` contract rather than claiming a full live-site visual comparison.
