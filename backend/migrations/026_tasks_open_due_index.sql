-- Shrink the active-deadline index and avoid indexing finished/undated tasks.
-- Supports overview()'s WHERE workspace_id=? AND due_date!='' AND status!='done'.
CREATE INDEX IF NOT EXISTS idx_tasks_workspace_open_due
    ON tasks(workspace_id, due_date)
    WHERE due_date <> '' AND status <> 'done';

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (36, strftime('%s', 'now'));
