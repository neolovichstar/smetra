-- SQLite schema additions are applied idempotently by backend.business.ensure_schema.
-- Version 35 records the matching PostgreSQL AI provenance migration series.
INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (35, strftime('%s', 'now'));
