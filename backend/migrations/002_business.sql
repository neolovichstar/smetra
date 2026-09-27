CREATE TABLE IF NOT EXISTS workspaces (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
 currency TEXT NOT NULL DEFAULT 'RUB', settings TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS workspace_members (
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('owner','admin','manager','member','viewer')),
 PRIMARY KEY(workspace_id,user_id)
);
CREATE TABLE IF NOT EXISTS clients (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 name TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'person', company TEXT NOT NULL DEFAULT '',
 email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', telegram TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]', custom_fields TEXT NOT NULL DEFAULT '{}',
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_clients_workspace ON clients(workspace_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS catalog_items (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL DEFAULT 'шт.',
 price INTEGER NOT NULL DEFAULT 0 CHECK(price>=0), cost_price INTEGER NOT NULL DEFAULT 0 CHECK(cost_price>=0),
 tax TEXT NOT NULL DEFAULT '0', category TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_catalog_workspace ON catalog_items(workspace_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS quote_items (
 id TEXT PRIMARY KEY, quote_id TEXT NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, data TEXT NOT NULL, UNIQUE(quote_id,position)
);
CREATE TABLE IF NOT EXISTS quote_versions (
 quote_id TEXT NOT NULL REFERENCES quotes(id) ON DELETE CASCADE, version INTEGER NOT NULL,
 snapshot TEXT NOT NULL, author_id TEXT REFERENCES users(id) ON DELETE SET NULL,
 comment TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, PRIMARY KEY(quote_id,version)
);
CREATE TABLE IF NOT EXISTS activity (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 actor_id TEXT REFERENCES users(id) ON DELETE SET NULL, entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_workspace ON activity(workspace_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_entity ON activity(workspace_id,entity_id,created_at DESC);
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 quote_id TEXT UNIQUE REFERENCES quotes(id) ON DELETE SET NULL, quote_version INTEGER,
 client_id TEXT REFERENCES clients(id) ON DELETE SET NULL, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'planned',
 amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks>=0), internal_cost INTEGER NOT NULL DEFAULT 0,
 currency TEXT NOT NULL DEFAULT 'RUB', due_date TEXT NOT NULL DEFAULT '',
 custom_fields TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 1,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_workspace ON projects(workspace_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS project_stages (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL DEFAULT '',
 amount_kopecks INTEGER NOT NULL DEFAULT 0 CHECK(amount_kopecks>=0), status TEXT NOT NULL DEFAULT 'planned',
 assignee TEXT REFERENCES users(id) ON DELETE SET NULL, revision INTEGER NOT NULL DEFAULT 1,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stages_project ON project_stages(workspace_id,project_id);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 project_id TEXT REFERENCES projects(id) ON DELETE CASCADE, client_id TEXT REFERENCES clients(id) ON DELETE SET NULL,
 name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL DEFAULT '',
 priority TEXT NOT NULL DEFAULT 'normal', status TEXT NOT NULL DEFAULT 'todo',
 assignee TEXT REFERENCES users(id) ON DELETE SET NULL, revision INTEGER NOT NULL DEFAULT 1,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks(workspace_id,due_date);
CREATE TABLE IF NOT EXISTS leads (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 client_id TEXT REFERENCES clients(id) ON DELETE SET NULL, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Новый',
 amount_kopecks INTEGER NOT NULL DEFAULT 0 CHECK(amount_kopecks>=0), revision INTEGER NOT NULL DEFAULT 1,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_workspace ON leads(workspace_id,status,updated_at DESC);
CREATE TABLE IF NOT EXISTS project_payments (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 stage_id TEXT REFERENCES project_stages(id) ON DELETE SET NULL,
 amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks>0), payment_date TEXT NOT NULL,
 method TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', idempotency_key TEXT NOT NULL,
 created_at INTEGER NOT NULL, UNIQUE(workspace_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_project_payments_project ON project_payments(workspace_id,project_id);
CREATE TABLE IF NOT EXISTS expenses (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks>0), category TEXT NOT NULL,
 expense_date TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', idempotency_key TEXT NOT NULL,
 created_at INTEGER NOT NULL, UNIQUE(workspace_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_expenses_project ON expenses(workspace_id,project_id);
CREATE TABLE IF NOT EXISTS comments (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 quote_id TEXT NOT NULL REFERENCES quotes(id) ON DELETE CASCADE, author TEXT NOT NULL,
 message TEXT NOT NULL, public INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_quote ON comments(quote_id,created_at);
CREATE TABLE IF NOT EXISTS notifications (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 message TEXT NOT NULL, entity_id TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_workspace ON notifications(workspace_id,created_at DESC);
CREATE TABLE IF NOT EXISTS notification_reads (
 notification_id TEXT NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(notification_id,user_id)
);
CREATE TABLE IF NOT EXISTS custom_field_definitions (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 entity_type TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL, options TEXT NOT NULL DEFAULT '[]',
 created_at INTEGER NOT NULL, UNIQUE(workspace_id,entity_type,name)
);
CREATE TABLE IF NOT EXISTS estimate_templates (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 name TEXT NOT NULL, snapshot TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 quote_id TEXT REFERENCES quotes(id) ON DELETE SET NULL, project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
 name TEXT NOT NULL, kind TEXT NOT NULL, template TEXT NOT NULL, snapshot TEXT NOT NULL,
 number INTEGER NOT NULL, created_at INTEGER NOT NULL, UNIQUE(workspace_id,number)
);
CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id,created_at DESC);
