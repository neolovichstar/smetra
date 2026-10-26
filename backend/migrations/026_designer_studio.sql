-- Interior design workspace: separate from construction objects and quotes.
CREATE TABLE IF NOT EXISTS designer_projects (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 client_id TEXT REFERENCES clients(id) ON DELETE SET NULL,
 name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 budget_kopecks INTEGER NOT NULL DEFAULT 0 CHECK (budget_kopecks >= 0),
 revision INTEGER NOT NULL DEFAULT 1,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_designer_projects_workspace
 ON designer_projects(workspace_id,updated_at DESC);

CREATE TABLE IF NOT EXISTS designer_rooms (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES designer_projects(id) ON DELETE CASCADE,
 name TEXT NOT NULL,
 notes TEXT NOT NULL DEFAULT '',
 revision INTEGER NOT NULL DEFAULT 1,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_designer_rooms_project
 ON designer_rooms(workspace_id,project_id,created_at);

CREATE TABLE IF NOT EXISTS designer_items (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES designer_projects(id) ON DELETE CASCADE,
 room_id TEXT REFERENCES designer_rooms(id) ON DELETE SET NULL,
 kind TEXT NOT NULL,
 name TEXT NOT NULL,
 article TEXT NOT NULL DEFAULT '',
 supplier TEXT NOT NULL DEFAULT '',
 unit TEXT NOT NULL DEFAULT 'шт.',
 quantity TEXT NOT NULL DEFAULT '1',
 unit_price INTEGER NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
 notes TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'planned',
 revision INTEGER NOT NULL DEFAULT 1,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_designer_items_project
 ON designer_items(workspace_id,project_id,room_id,created_at);

INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(40,strftime('%s','now'));
