BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- This smaller partial index matches the active-deadline dashboard query.
CREATE INDEX IF NOT EXISTS idx_tasks_workspace_open_due
    ON smetra.tasks(workspace_id, due_date)
    WHERE due_date <> '' AND status <> 'done';

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (39, extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
