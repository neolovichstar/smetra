# Scheduled encrypted PostgreSQL backups

## Deployment status

The workflow is at .github/workflows/postgres-backup.yml. It executes every day at 04:37 UTC only if present on GitHub's **default branch**. Do not merge the old main branch into production: as of 2026-10-28 it is behind the live deployment. The new workflow has to be safely integrated into the default branch, with Vercel deployment rules checked first.

**A successful CI test is not a stored production backup.** Until the credentials below are configured and a real workflow run uploads an archive, there are no verified scheduled backups. GitHub Actions artifacts are temporary (30-day retention), not a full disaster-recovery solution.

## One-time owner setup

1. Install [age](https://github.com/FiloSottile/age/releases) on a trusted local machine, and create your **offline private decryption key**:

   ```sh
   age-keygen -o smetra-backup-identity.txt
   age-keygen -y smetra-backup-identity.txt
   ```

   Keep the private file in at least two protected offline locations. Do NOT upload it to GitHub, Supabase, Upstash, Vercel, ChatGPT or the repository. If it is lost, you cannot recover the backups.

2. In GitHub → repository Settings → Secrets and variables → Actions, create the **repository variable** `SMETRA_BACKUP_AGE_RECIPIENT` containing the public value from `age-keygen -y` (begins with `age1`).

3. Create the **repository secret** `SMETRA_BACKUP_DATABASE_URL`. Copy the real PostgreSQL **session-mode pooler** connection string (port 5432) from Supabase → Connect and set `sslmode=require`. Do not guess the hostname. The Supabase Free direct connection requires IPv6, which GitHub-hosted runners may not support. The transaction pooler (port 6543) is unsuitable for exported snapshots. The account must be able to export all `smetra` data (privileged role; do not put in client-side settings).

4. Safely integrate the reviewed workflow and backup tool onto GitHub's default branch. The code currently deployed by Vercel is on a newer branch than main. Do not merge automatically until the Vercel production branch is protected from a stale redeploy.

5. Trigger GitHub Actions → Encrypted PostgreSQL backup → Run workflow. Verify that it finished green, produced only `*.tar.age` and `*.sha256`, and that a restore drill passed. Inspect GitHub Action failures daily. Enable GitHub Action failure emails.

## Restore drill: use an isolated computer and database

Download the artifact. On the trusted computer with the offline key:

```sh
sha256sum -c smetra-DATE-runID.tar.age.sha256
mkdir -m 700 /private/smetra-restore
age -d -i /secure/smetra-backup-identity.txt -o /private/smetra-restore/backup.tar smetra-DATE-runID.tar.age
tar -tf /private/smetra-restore/backup.tar
tar -xf /private/smetra-restore/backup.tar -C /private/smetra-restore
```

Prepare a fresh PostgreSQL 17 database named `smetra_restore_...` **on loopback only**, with necessary platform schemas and roles. Then invoke the tested `backend.manage restore-check` command against the extracted `*.dump` file. It validates checksum, row fingerprints, indexes, grants, constraints and RLS policies; it refuses an occupied schema. A running production database must never be used as the restore target.

## Scope and limitations

- A dump of private schema `smetra` does NOT include Supabase Storage objects, files held by other external providers, Auth data in other schemas, or the Supabase configuration. Back these up separately.
- GitHub Actions scheduled workflows run only on the default branch, can be delayed or skipped, and may be disabled for inactive public repositories. Record the timestamp of the most recent **successful artifact**, not just the last workflow.
- Free GitHub artifacts expire after 30 days. Configure durable, private, versioned off-site storage when affordable and legally appropriate. Cloudflare R2 is not enabled in the current account; Upstash Free already has one public bucket and rejects another private one.
- Encrypt BEFORE publishing: the workflow uploads only ciphertext and a SHA-256 sidecar. Only the **public** age recipient is on the runner; the private key must never be provided as a CI secret.
- Do not restore production during live payment processing. Reconcile payment provider events and explicitly check idempotency before re-enabling workers.
