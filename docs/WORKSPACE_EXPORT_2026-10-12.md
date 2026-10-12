# Unified workspace export

This release adds owner-only export from **Settings → Export data**. The browser builds a single ZIP while the API sends small, authenticated pages instead of a large Vercel response.

The archive contains JSON for CRM, estimates and their revisions, catalog and price history, projects, work stages, tasks, leads, receipts and expenses, documents, notifications, workspace knowledge, the current user's assistant conversations and profile, and construction objects, measurements, work logs, defects, purchases and change orders. Uploaded files and retained file revisions are separate entries. SHA-256 and byte length are verified before each file enters the ZIP. Editing or deleting a file during export stops the operation.

Export routes require the authenticated owner membership of the selected workspace. Pages and downloads are scoped to that workspace and rate-limited. Workspace team email/profile data, credentials, sessions, OAuth state and tickets, payment secrets, assistant job/action leases, public intake tokens, public change/estimate links, file storage paths, and idempotency keys are omitted. Assistant history and profile data include only the current user. No database migration is required.

The ZIP uses UTF-8 names and uncompressed entries so it can be written incrementally without a CDN or a large compression dependency. Browsers with the File System Access API write directly to the chosen file; other browsers use a Blob download. The current export is a backup format, not an import/restore flow. For a consistent snapshot, avoid editing workspace data while the archive is being created.

Validation: focused integration verifies every allowlisted table route, owner enforcement, file isolation, digest-checked current file and historical revision downloads, and secret redaction. A Node browser-runtime fixture builds the ZIP; Python's standard ZIP reader verifies its directory, JSON payload, and uploaded file bytes.
