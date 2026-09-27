-- Private server-only schema; existing Supabase schemas are untouched.
BEGIN;

CREATE SCHEMA IF NOT EXISTS smetra;

REVOKE ALL ON SCHEMA smetra FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS smetra.users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
 blocked BIGINT NOT NULL DEFAULT 0 CHECK(blocked IN (0,1)),
 plan TEXT NOT NULL DEFAULT 'free', entitlement_until BIGINT NOT NULL DEFAULT 0,
 created_at BIGINT NOT NULL, deleted_at BIGINT, email_verified_at BIGINT
);

CREATE TABLE IF NOT EXISTS smetra.sessions (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL UNIQUE, expires_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON smetra.sessions(user_id);

CREATE TABLE IF NOT EXISTS smetra.email_tokens (
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL UNIQUE,purpose TEXT NOT NULL CHECK(purpose IN ('verify','reset')),
 expires_at BIGINT NOT NULL,consumed_at BIGINT
);

CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON smetra.email_tokens(user_id,purpose);

CREATE TABLE IF NOT EXISTS smetra.quotes (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, client TEXT NOT NULL, description TEXT NOT NULL,
 amount_kopecks BIGINT NOT NULL CHECK(amount_kopecks > 0),
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','sent','accepted','declined','completed')),
 public_token TEXT NOT NULL UNIQUE, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quotes_user_created ON smetra.quotes(user_id,created_at DESC);

CREATE TABLE IF NOT EXISTS smetra.payments (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 provider_id TEXT NOT NULL UNIQUE, plan TEXT NOT NULL,
 amount_kopecks BIGINT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','succeeded','canceled')),
 idempotency_key TEXT NOT NULL, confirmation_url TEXT NOT NULL, created_at BIGINT NOT NULL,
 activated_at BIGINT,
 UNIQUE(user_id,idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_payments_user ON smetra.payments(user_id,created_at DESC);

CREATE TABLE IF NOT EXISTS smetra.refunds (
 id TEXT PRIMARY KEY, payment_id TEXT NOT NULL REFERENCES smetra.payments(id),
 provider_id TEXT NOT NULL UNIQUE, amount_kopecks BIGINT NOT NULL,
 status TEXT NOT NULL, created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS smetra.events (
 id TEXT PRIMARY KEY,user_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 name TEXT NOT NULL,created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_name ON smetra.events(name,created_at);

CREATE TABLE IF NOT EXISTS smetra.support (
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 message TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('open','closed')),created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS smetra.audit (
 id TEXT PRIMARY KEY,actor_id TEXT,action TEXT NOT NULL,target TEXT NOT NULL,
 detail TEXT NOT NULL DEFAULT '',created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS smetra.workspaces (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES smetra.users(id), name TEXT NOT NULL,
 currency TEXT NOT NULL DEFAULT 'RUB', settings TEXT NOT NULL DEFAULT '{}', created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS smetra.workspace_members (
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('owner','admin','manager','member','viewer')),
 PRIMARY KEY(workspace_id,user_id)
);

CREATE TABLE IF NOT EXISTS smetra.clients (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 name TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'person', company TEXT NOT NULL DEFAULT '',
 email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', telegram TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]', custom_fields TEXT NOT NULL DEFAULT '{}',
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, revision BIGINT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_clients_workspace ON smetra.clients(workspace_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.catalog_items (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL DEFAULT 'шт.',
 price BIGINT NOT NULL DEFAULT 0 CHECK(price>=0), cost_price BIGINT NOT NULL DEFAULT 0 CHECK(cost_price>=0),
 tax TEXT NOT NULL DEFAULT '0', category TEXT NOT NULL DEFAULT '', active BIGINT NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, revision BIGINT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_catalog_workspace ON smetra.catalog_items(workspace_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.quote_items (
 id TEXT PRIMARY KEY, quote_id TEXT NOT NULL REFERENCES smetra.quotes(id) ON DELETE CASCADE,
 position BIGINT NOT NULL, data TEXT NOT NULL, UNIQUE(quote_id,position)
);

CREATE TABLE IF NOT EXISTS smetra.quote_versions (
 quote_id TEXT NOT NULL REFERENCES smetra.quotes(id) ON DELETE CASCADE, version BIGINT NOT NULL,
 snapshot TEXT NOT NULL, author_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 comment TEXT NOT NULL DEFAULT '', created_at BIGINT NOT NULL, PRIMARY KEY(quote_id,version)
);

CREATE TABLE IF NOT EXISTS smetra.activity (
 rowid BIGINT GENERATED ALWAYS AS IDENTITY,
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 actor_id TEXT REFERENCES smetra.users(id) ON DELETE SET NULL, entity_type TEXT NOT NULL,
 entity_id TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_workspace ON smetra.activity(workspace_id,created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activity_entity ON smetra.activity(workspace_id,entity_id,created_at DESC);

CREATE TABLE IF NOT EXISTS smetra.projects (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 quote_id TEXT UNIQUE REFERENCES smetra.quotes(id) ON DELETE SET NULL, quote_version BIGINT,
 client_id TEXT REFERENCES smetra.clients(id) ON DELETE SET NULL, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'planned',
 amount_kopecks BIGINT NOT NULL CHECK(amount_kopecks>=0), internal_cost BIGINT NOT NULL DEFAULT 0,
 currency TEXT NOT NULL DEFAULT 'RUB', due_date TEXT NOT NULL DEFAULT '',
 custom_fields TEXT NOT NULL DEFAULT '{}', revision BIGINT NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_workspace ON smetra.projects(workspace_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.project_stages (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES smetra.projects(id) ON DELETE CASCADE, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL DEFAULT '',
 amount_kopecks BIGINT NOT NULL DEFAULT 0 CHECK(amount_kopecks>=0), status TEXT NOT NULL DEFAULT 'planned',
 assignee TEXT REFERENCES smetra.users(id) ON DELETE SET NULL, revision BIGINT NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stages_project ON smetra.project_stages(workspace_id,project_id);

CREATE TABLE IF NOT EXISTS smetra.tasks (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 project_id TEXT REFERENCES smetra.projects(id) ON DELETE CASCADE, client_id TEXT REFERENCES smetra.clients(id) ON DELETE SET NULL,
 name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL DEFAULT '',
 priority TEXT NOT NULL DEFAULT 'normal', status TEXT NOT NULL DEFAULT 'todo',
 assignee TEXT REFERENCES smetra.users(id) ON DELETE SET NULL, revision BIGINT NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON smetra.tasks(workspace_id,due_date);

CREATE TABLE IF NOT EXISTS smetra.leads (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 client_id TEXT REFERENCES smetra.clients(id) ON DELETE SET NULL, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Новый',
 amount_kopecks BIGINT NOT NULL DEFAULT 0 CHECK(amount_kopecks>=0), revision BIGINT NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_workspace ON smetra.leads(workspace_id,status,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.project_payments (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES smetra.projects(id) ON DELETE CASCADE,
 stage_id TEXT REFERENCES smetra.project_stages(id) ON DELETE SET NULL,
 amount_kopecks BIGINT NOT NULL CHECK(amount_kopecks>0), payment_date TEXT NOT NULL,
 method TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', idempotency_key TEXT NOT NULL,
 created_at BIGINT NOT NULL, UNIQUE(workspace_id,idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_project_payments_project ON smetra.project_payments(workspace_id,project_id);

CREATE TABLE IF NOT EXISTS smetra.expenses (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES smetra.projects(id) ON DELETE CASCADE,
 amount_kopecks BIGINT NOT NULL CHECK(amount_kopecks>0), category TEXT NOT NULL,
 expense_date TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', idempotency_key TEXT NOT NULL,
 created_at BIGINT NOT NULL, UNIQUE(workspace_id,idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_expenses_project ON smetra.expenses(workspace_id,project_id);

CREATE TABLE IF NOT EXISTS smetra.comments (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 quote_id TEXT NOT NULL REFERENCES smetra.quotes(id) ON DELETE CASCADE, author TEXT NOT NULL,
 message TEXT NOT NULL, public BIGINT NOT NULL DEFAULT 1, created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comments_quote ON smetra.comments(quote_id,created_at);

CREATE TABLE IF NOT EXISTS smetra.notifications (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 message TEXT NOT NULL, entity_id TEXT NOT NULL, created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notifications_workspace ON smetra.notifications(workspace_id,created_at DESC);

CREATE TABLE IF NOT EXISTS smetra.notification_reads (
 notification_id TEXT NOT NULL REFERENCES smetra.notifications(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE, PRIMARY KEY(notification_id,user_id)
);

CREATE TABLE IF NOT EXISTS smetra.custom_field_definitions (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 entity_type TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL, options TEXT NOT NULL DEFAULT '[]',
 created_at BIGINT NOT NULL, UNIQUE(workspace_id,entity_type,name)
);

CREATE TABLE IF NOT EXISTS smetra.estimate_templates (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 name TEXT NOT NULL, snapshot TEXT NOT NULL, created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS smetra.documents (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 quote_id TEXT REFERENCES smetra.quotes(id) ON DELETE SET NULL, project_id TEXT REFERENCES smetra.projects(id) ON DELETE SET NULL,
 name TEXT NOT NULL, kind TEXT NOT NULL, template TEXT NOT NULL, snapshot TEXT NOT NULL,
 number BIGINT NOT NULL, created_at BIGINT NOT NULL, UNIQUE(workspace_id,number)
);

CREATE INDEX IF NOT EXISTS idx_documents_workspace ON smetra.documents(workspace_id,created_at DESC);

CREATE TABLE IF NOT EXISTS smetra.files (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 quote_id TEXT REFERENCES smetra.quotes(id) ON DELETE CASCADE,
 project_id TEXT REFERENCES smetra.projects(id) ON DELETE CASCADE,
 client_id TEXT REFERENCES smetra.clients(id) ON DELETE CASCADE,
 name TEXT NOT NULL, mime TEXT NOT NULL, size BIGINT NOT NULL CHECK(size>0),
 sha256 TEXT NOT NULL, storage_name TEXT NOT NULL UNIQUE,
 public BIGINT NOT NULL DEFAULT 0 CHECK(public IN (0,1)), created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_workspace ON smetra.files(workspace_id,created_at DESC);

CREATE INDEX IF NOT EXISTS idx_files_quote ON smetra.files(quote_id,public);

CREATE TABLE IF NOT EXISTS smetra.ai_usage (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 action TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
 input_tokens BIGINT NOT NULL DEFAULT 0, output_tokens BIGINT NOT NULL DEFAULT 0,
 created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_user ON smetra.ai_usage(user_id,created_at DESC);

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES smetra.workspaces(id);

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS client_id TEXT REFERENCES smetra.clients(id) ON DELETE SET NULL;

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'RUB';

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS revision BIGINT NOT NULL DEFAULT 1;

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS published_version BIGINT NOT NULL DEFAULT 0;

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS approval_state TEXT NOT NULL DEFAULT 'draft';

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS terms TEXT NOT NULL DEFAULT '';

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS due_date TEXT NOT NULL DEFAULT '';

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS expires_at BIGINT;

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS internal_cost BIGINT NOT NULL DEFAULT 0;

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS view_count BIGINT NOT NULL DEFAULT 0;

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS first_viewed_at BIGINT;

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS sent_at BIGINT;

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS approved_at BIGINT;

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS approved_by TEXT NOT NULL DEFAULT '';

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS custom_fields TEXT NOT NULL DEFAULT '{}';

ALTER TABLE smetra.quotes ADD COLUMN IF NOT EXISTS itemized BIGINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_quotes_workspace ON smetra.quotes(workspace_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.schema_migrations(version BIGINT PRIMARY KEY,applied_at BIGINT NOT NULL);

CREATE TABLE IF NOT EXISTS smetra.file_payloads(file_id TEXT PRIMARY KEY REFERENCES smetra.files(id) ON DELETE CASCADE,content BYTEA NOT NULL);

CREATE TABLE IF NOT EXISTS smetra.rate_limits(key TEXT PRIMARY KEY,count BIGINT NOT NULL,started BIGINT NOT NULL);

CREATE INDEX IF NOT EXISTS idx_rate_limits_started ON smetra.rate_limits(started);

INSERT INTO smetra.schema_migrations VALUES(4,extract(epoch FROM now())::BIGINT) ON CONFLICT DO NOTHING;

ALTER TABLE smetra.activity ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.ai_usage ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.audit ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.catalog_items ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.clients ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.comments ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.custom_field_definitions ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.documents ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.email_tokens ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.estimate_templates ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.events ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.expenses ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.file_payloads ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.files ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.leads ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.notification_reads ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.notifications ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.payments ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.project_payments ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.project_stages ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.projects ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.quote_items ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.quote_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.quotes ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.rate_limits ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.refunds ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.schema_migrations ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.sessions ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.support ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.tasks ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.users ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.workspace_members ENABLE ROW LEVEL SECURITY;

ALTER TABLE smetra.workspaces ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON ALL TABLES IN SCHEMA smetra FROM PUBLIC, anon, authenticated;

COMMIT;
