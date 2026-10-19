-- Keep foreign-key cleanup and ownership/device lookups indexed without
-- changing existing queue ordering indexes.
CREATE INDEX IF NOT EXISTS idx_push_outbox_workspace_id
    ON push_outbox(workspace_id);
CREATE INDEX IF NOT EXISTS idx_push_outbox_notification_id
    ON push_outbox(notification_id);
CREATE INDEX IF NOT EXISTS idx_push_deliveries_workspace_id
    ON push_deliveries(workspace_id);
CREATE INDEX IF NOT EXISTS idx_push_deliveries_device_id
    ON push_deliveries(device_id);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (34, strftime('%s', 'now'));
