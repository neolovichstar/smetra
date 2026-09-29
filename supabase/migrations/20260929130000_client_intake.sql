BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE IF NOT EXISTS smetra.intake_forms (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL UNIQUE REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 token TEXT NOT NULL UNIQUE, title TEXT NOT NULL DEFAULT 'Оставить заявку',
 enabled BIGINT NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS smetra.client_requests (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 form_id TEXT NOT NULL REFERENCES smetra.intake_forms(id) ON DELETE CASCADE,
 client_id TEXT NOT NULL REFERENCES smetra.clients(id) ON DELETE CASCADE,
 lead_id TEXT NOT NULL UNIQUE REFERENCES smetra.leads(id) ON DELETE CASCADE,
 details TEXT NOT NULL, budget_kopecks BIGINT NOT NULL DEFAULT 0 CHECK(budget_kopecks>=0),
 due_date TEXT NOT NULL DEFAULT '', comment TEXT NOT NULL DEFAULT '',
 created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_client_requests_workspace ON smetra.client_requests(workspace_id,created_at DESC);
ALTER TABLE smetra.intake_forms ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.client_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON smetra.intake_forms FROM PUBLIC,anon,authenticated;
REVOKE ALL ON smetra.client_requests FROM PUBLIC,anon,authenticated;
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(6,EXTRACT(EPOCH FROM now())::BIGINT) ON CONFLICT DO NOTHING;
COMMIT;
