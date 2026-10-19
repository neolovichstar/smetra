BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- The queue-ordering indexes do not cover these foreign keys because the
-- foreign-key columns are not the leading columns of an existing index.
CREATE INDEX IF NOT EXISTS idx_push_outbox_workspace_id
    ON smetra.push_outbox(workspace_id);
CREATE INDEX IF NOT EXISTS idx_push_outbox_notification_id
    ON smetra.push_outbox(notification_id);
CREATE INDEX IF NOT EXISTS idx_push_deliveries_workspace_id
    ON smetra.push_deliveries(workspace_id);
CREATE INDEX IF NOT EXISTS idx_push_deliveries_device_id
    ON smetra.push_deliveries(device_id);

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (34, extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
