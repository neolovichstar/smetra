-- Version 71: bounded, privacy-minimal first-party visit statistics.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
CREATE TABLE IF NOT EXISTS smetra.site_visits(
 id TEXT PRIMARY KEY,
 day INTEGER NOT NULL,
 visitor_hash TEXT NOT NULL CHECK(length(visitor_hash)=64),
 page TEXT NOT NULL CHECK(page IN ('landing','app')),
 views INTEGER NOT NULL DEFAULT 1 CHECK(views BETWEEN 1 AND 100),
 created_at BIGINT NOT NULL,
 UNIQUE(day,visitor_hash,page)
);
CREATE INDEX IF NOT EXISTS idx_site_visits_created ON smetra.site_visits(created_at);
CREATE INDEX IF NOT EXISTS idx_site_visits_day ON smetra.site_visits(day);
ALTER TABLE smetra.site_visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.site_visits FORCE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.site_visits FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON smetra.site_visits TO smetra_runtime;
CREATE POLICY site_visits_backend_only ON smetra.site_visits
 FOR ALL TO smetra_runtime USING(true) WITH CHECK(true);
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(71,extract(epoch FROM now())::bigint) ON CONFLICT(version) DO NOTHING;
COMMIT;
