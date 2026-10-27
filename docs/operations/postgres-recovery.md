# PostgreSQL recovery: «сметра.»

The application uses a private `smetra` schema in Supabase PostgreSQL.
This runbook covers a **logical application-schema copy**, not an entire Supabase
project, and makes no claim that a scheduled off-site backup already exists.

## Mandatory production checklist

1. Check whether the Supabase organization plan includes daily backups.
   On Free, **do not rely on managed daily backups**. Keep verified copies
   outside the account/project that holds the database.
2. Run `backup` from a trusted, persistent worker with PostgreSQL **17**
   client binaries, network access and an appropriately scoped DB credential.
   Never run a backup inside a transient Vercel request. Do not put DSNs,
   passwords, dump files or manifests into Git or public CI artifacts.
3. Encrypt both the `.dump` and `.dump.json` files before upload to access-
   controlled off-site storage. Set lifecycle/retention and deletion rules;
   record last success and alert when no valid recent backup exists.
4. Regularly test a restore in a fresh isolated local environment. A dump
   being created successfully is **not** proof it can be restored.
5. Save other critical components independently: Supabase Storage **objects**
   (not just their DB metadata), Auth configuration if used, custom role
   definitions/passwords, environment secrets, OAuth settings, and any other
   external file/blob stores. Restoring DB data alone will not recreate them.

## Commands (run on a trusted operator machine)

Keep `DATABASE_URL` in your secure environment, not in shell history.
Never use a production database as `RESTORE_DATABASE_URL`.

```sh
python -m backend.manage check
python -m backend.manage backup --output /private/backups/smetra-UTC-timestamp.dump

# Create an **empty local** database named smetra_restore_drill and prepare
# required custom roles/platform dependencies before invoking this command.
RESTORE_DATABASE_URL='postgresql://localhost/smetra_restore_drill' \
  python -m backend.manage restore-check \
  --archive /private/backups/smetra-UTC-timestamp.dump
```

The backup command refuses to overwrite an existing dump or manifest.
It exports a consistent PostgreSQL snapshot with `pg_dump --format=custom`
and writes a SHA-256 manifest with row fingerprints and metadata hashes.
The restore check verifies checksum, row content, constraints, indexes,
grants and RLS policies. The restore target is restricted to a loopback
PostgreSQL instance and to database names matching `smetra_restore_*`;
it also refuses to restore over an existing `smetra` schema.

Restore prerequisites include compatible PostgreSQL server/client versions
and the platform/custom roles needed by the app. `--no-owner` does **not**
create roles referenced by GRANTs. A production disaster recovery procedure
must recreate platform dependencies in the right order, validate access,
then re-enable the application only after consistency and payment
reconciliation checks pass. Never run a payment or email worker on a newly
restored DB until replay/idempotency has been checked.

## Operational readiness

The CI job can prove isolated logical backup/restore compatibility, but
it does not execute a real production backup or measure recovery-point age.
Before marking production as protected, record in operational monitoring:

- Timestamp of latest successful encrypted **off-site** copy.
- Age of latest **successfully restored** copy and number of verified tables.
- Recovery point and maximum acceptable loss (RPO), measured recovery
  duration (RTO), and where key material is held.
- Separate availability of file objects, payment-provider event history
  and authentication configuration.
