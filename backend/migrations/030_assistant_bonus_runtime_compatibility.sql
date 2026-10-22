CREATE INDEX IF NOT EXISTS idx_assistant_jobs_bonus_grant ON assistant_jobs(bonus_grant_id) WHERE bonus_grant_id IS NOT NULL;
INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(33,CAST(strftime('%s','now') AS INTEGER));
