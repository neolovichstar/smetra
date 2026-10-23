-- Opaque capabilities for invalidation-only Realtime broadcasts.
CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_realtime_topic
  ON conversations(realtime_topic) WHERE realtime_topic IS NOT NULL AND realtime_topic<>'';
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_directory_inbox_topic
  ON user_directory(inbox_topic) WHERE inbox_topic IS NOT NULL AND inbox_topic<>'';
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_realtime_topic
  ON workspaces(realtime_topic) WHERE realtime_topic IS NOT NULL AND realtime_topic<>'';
INSERT OR IGNORE INTO schema_migrations(version,applied_at)
VALUES(36,CAST(strftime('%s','now') AS INTEGER));
