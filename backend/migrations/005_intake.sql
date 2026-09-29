CREATE TABLE IF NOT EXISTS intake_forms (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL UNIQUE REFERENCES workspaces(id) ON DELETE CASCADE,
 token TEXT NOT NULL UNIQUE, title TEXT NOT NULL DEFAULT 'Оставить заявку',
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS client_requests (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 form_id TEXT NOT NULL REFERENCES intake_forms(id) ON DELETE CASCADE,
 client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
 lead_id TEXT NOT NULL UNIQUE REFERENCES leads(id) ON DELETE CASCADE,
 details TEXT NOT NULL, budget_kopecks INTEGER NOT NULL DEFAULT 0 CHECK(budget_kopecks>=0),
 due_date TEXT NOT NULL DEFAULT '', comment TEXT NOT NULL DEFAULT '',
 created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_client_requests_workspace ON client_requests(workspace_id,created_at DESC);
