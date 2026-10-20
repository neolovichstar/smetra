-- Version 35: legal acceptance metadata and AI-draft origin are ensured
-- by the guarded schema upgrades in backend/app.py and backend/business.py.
-- Keep an explicit marker so local installations can audit their schema level.
INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (35, strftime('%s', 'now'));
