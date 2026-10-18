BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE INDEX IF NOT EXISTS idx_projects_client_id ON smetra.projects(client_id);
CREATE INDEX IF NOT EXISTS idx_project_stages_project_id ON smetra.project_stages(project_id);
CREATE INDEX IF NOT EXISTS idx_project_stages_assignee ON smetra.project_stages(assignee);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON smetra.tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_client_id ON smetra.tasks(client_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON smetra.tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_project_payments_project_id ON smetra.project_payments(project_id);
CREATE INDEX IF NOT EXISTS idx_project_payments_stage_id ON smetra.project_payments(stage_id);
CREATE INDEX IF NOT EXISTS idx_comments_workspace_created ON smetra.comments(workspace_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_quotes_client_id ON smetra.quotes(client_id);
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON smetra.documents(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_quote_id ON smetra.documents(quote_id);
CREATE INDEX IF NOT EXISTS idx_files_project_id ON smetra.files(project_id);
CREATE INDEX IF NOT EXISTS idx_files_client_id ON smetra.files(client_id);
CREATE INDEX IF NOT EXISTS idx_files_construction_id ON smetra.files(construction_id);
CREATE INDEX IF NOT EXISTS idx_expenses_project_id ON smetra.expenses(project_id);
CREATE INDEX IF NOT EXISTS idx_notification_reads_user ON smetra.notification_reads(user_id);
CREATE INDEX IF NOT EXISTS idx_assistant_jobs_conversation_id ON smetra.assistant_jobs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_assistant_jobs_file_id ON smetra.assistant_jobs(file_id);
CREATE INDEX IF NOT EXISTS idx_assistant_jobs_user_id ON smetra.assistant_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_assistant_messages_user_id ON smetra.assistant_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner_id ON smetra.workspaces(owner_id);
CREATE INDEX IF NOT EXISTS idx_events_user_id_created ON smetra.events(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_actor_id ON smetra.activity(actor_id);
CREATE INDEX IF NOT EXISTS idx_catalog_price_history_item_id ON smetra.catalog_price_history(item_id);

INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(32,extract(epoch FROM now())::BIGINT) ON CONFLICT DO NOTHING;
COMMIT;
