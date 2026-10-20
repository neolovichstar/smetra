-- Target the dashboard lists, quota check and detail panels without
-- duplicating existing workspace/created-at indexes.
CREATE INDEX IF NOT EXISTS idx_events_user_name
    ON events(user_id, name);
CREATE INDEX IF NOT EXISTS idx_quotes_workspace_approval_updated
    ON quotes(workspace_id, approval_state, updated_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_quotes_workspace_approved_at
    ON quotes(workspace_id, approved_at DESC)
    WHERE approved_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quotes_workspace_sent_at
    ON quotes(workspace_id, sent_at)
    WHERE sent_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quotes_workspace_first_viewed
    ON quotes(workspace_id, first_viewed_at DESC)
    WHERE first_viewed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_workspace_due_status
    ON projects(workspace_id, due_date, status);
CREATE INDEX IF NOT EXISTS idx_project_payments_workspace_project_created
    ON project_payments(workspace_id, project_id, created_at DESC);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (35, strftime('%s', 'now'));
