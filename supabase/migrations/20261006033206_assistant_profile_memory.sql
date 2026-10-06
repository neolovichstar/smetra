BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE smetra.user_profiles (
 user_id TEXT PRIMARY KEY REFERENCES smetra.users(id) ON DELETE CASCADE,
 first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '',
 profession TEXT NOT NULL DEFAULT '', company TEXT NOT NULL DEFAULT '', about TEXT NOT NULL DEFAULT '',
 response_style TEXT NOT NULL DEFAULT 'concise' CHECK(response_style IN ('concise','balanced','detailed')),
 memory_enabled INTEGER NOT NULL DEFAULT 1 CHECK(memory_enabled IN (0,1)), updated_at BIGINT NOT NULL
);
CREATE TABLE smetra.assistant_memory (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, title_key TEXT NOT NULL, content TEXT NOT NULL,
 source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual','assistant')),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, UNIQUE(workspace_id,user_id,title_key)
);
CREATE INDEX idx_assistant_memory_user ON smetra.assistant_memory(user_id,workspace_id,updated_at DESC);
ALTER TABLE smetra.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.user_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_memory FORCE ROW LEVEL SECURITY;
GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.user_profiles,smetra.assistant_memory TO smetra_runtime;
REVOKE ALL ON smetra.user_profiles,smetra.assistant_memory FROM PUBLIC,anon,authenticated;
CREATE POLICY smetra_runtime_profile ON smetra.user_profiles FOR ALL TO smetra_runtime
 USING (user_id=smetra.runtime_user_id()) WITH CHECK (user_id=smetra.runtime_user_id());
CREATE POLICY smetra_runtime_memory ON smetra.assistant_memory FOR ALL TO smetra_runtime
 USING (user_id=smetra.runtime_user_id() AND workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (user_id=smetra.runtime_user_id() AND workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
  AND smetra.runtime_workspace_allowed(workspace_id));
INSERT INTO smetra.schema_migrations(version,applied_at) VALUES(27,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
