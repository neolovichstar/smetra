BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='30s';
-- Ordered tenant-scoped chat reads; no data or permission changes.
CREATE INDEX IF NOT EXISTS idx_assistant_history_scope
 ON smetra.assistant_messages(workspace_id,user_id,conversation_id,created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_threads_pinned
 ON smetra.assistant_conversations(workspace_id,user_id,pinned DESC,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_actions_pending_feed
 ON smetra.assistant_actions(workspace_id,user_id,created_at DESC) WHERE status='pending';
CREATE INDEX IF NOT EXISTS idx_assistant_actions_applied_feed
 ON smetra.assistant_actions(workspace_id,user_id,created_at DESC) WHERE status='applied';
COMMIT;
