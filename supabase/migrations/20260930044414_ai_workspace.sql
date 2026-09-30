BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE IF NOT EXISTS smetra.assistant_conversations (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 title TEXT NOT NULL CHECK(length(title)<=120),
 context_entity TEXT NOT NULL DEFAULT '', context_id TEXT NOT NULL DEFAULT '',
 pinned BIGINT NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_conversations_user
 ON smetra.assistant_conversations(workspace_id,user_id,updated_at DESC);
ALTER TABLE smetra.assistant_messages
 ADD COLUMN IF NOT EXISTS conversation_id TEXT REFERENCES smetra.assistant_conversations(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_assistant_messages_conversation
 ON smetra.assistant_messages(conversation_id,created_at);

CREATE TABLE IF NOT EXISTS smetra.workspace_knowledge (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 title TEXT NOT NULL CHECK(length(title)<=120),
 content TEXT NOT NULL CHECK(length(content)<=12000),
 kind TEXT NOT NULL DEFAULT 'reference' CHECK(kind IN ('reference','rule')),
 enabled BIGINT NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 created_by TEXT REFERENCES smetra.users(id) ON DELETE SET NULL,
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspace_knowledge
 ON smetra.workspace_knowledge(workspace_id,enabled,updated_at DESC);

CREATE TABLE IF NOT EXISTS smetra.file_text_chunks (
 file_id TEXT NOT NULL REFERENCES smetra.files(id) ON DELETE CASCADE,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 page BIGINT NOT NULL CHECK(page>0),
 text TEXT NOT NULL CHECK(length(text)<=4000),
 source_sha256 TEXT NOT NULL,
 PRIMARY KEY(file_id,page)
);
CREATE INDEX IF NOT EXISTS idx_file_text_chunks_workspace
 ON smetra.file_text_chunks(workspace_id,file_id);

GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.assistant_conversations TO smetra_runtime;
ALTER TABLE smetra.assistant_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.assistant_conversations FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.assistant_conversations FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id) AND user_id=smetra.runtime_user_id())
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id) AND user_id=smetra.runtime_user_id());

GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.workspace_knowledge TO smetra_runtime;
ALTER TABLE smetra.workspace_knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.workspace_knowledge FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.workspace_knowledge FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id));

GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.file_text_chunks TO smetra_runtime;
ALTER TABLE smetra.file_text_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE smetra.file_text_chunks FORCE ROW LEVEL SECURITY;
CREATE POLICY smetra_runtime_scope ON smetra.file_text_chunks FOR ALL TO smetra_runtime
 USING (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id)
   AND EXISTS (SELECT 1 FROM smetra.files f WHERE f.id=file_id AND f.workspace_id=workspace_id))
 WITH CHECK (workspace_id=nullif(current_setting('smetra.workspace_id',true),'')
   AND smetra.runtime_workspace_allowed(workspace_id)
   AND EXISTS (SELECT 1 FROM smetra.files f WHERE f.id=file_id AND f.workspace_id=workspace_id));

REVOKE ALL ON smetra.assistant_conversations,smetra.workspace_knowledge,smetra.file_text_chunks FROM PUBLIC,anon,authenticated;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(8,extract(epoch FROM now())::bigint) ON CONFLICT DO NOTHING;
COMMIT;
