-- Add the first production-safe foundation for visual quote items, cloud imports and price monitoring.
-- Tokens are encrypted by the application; source documents remain in the provider's cloud.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE TABLE IF NOT EXISTS smetra.product_sources (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 quote_id TEXT NOT NULL REFERENCES smetra.quotes(id) ON DELETE CASCADE,
 quote_item_id TEXT NOT NULL REFERENCES smetra.quote_items(id) ON DELETE CASCADE,
 created_by TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 url TEXT NOT NULL,
 normalized_url TEXT NOT NULL,
 hostname TEXT NOT NULL,
 product_title TEXT NOT NULL DEFAULT '',
 brand TEXT NOT NULL DEFAULT '',
 sku TEXT NOT NULL DEFAULT '',
 image_url TEXT NOT NULL DEFAULT '',
 price_kopecks BIGINT CHECK(price_kopecks IS NULL OR price_kopecks >= 0),
 currency TEXT NOT NULL DEFAULT 'RUB',
 unit TEXT NOT NULL DEFAULT '',
 availability TEXT NOT NULL DEFAULT 'unknown'
   CHECK(availability IN ('in_stock','out_of_stock','preorder','backorder','unknown')),
 product_attributes TEXT NOT NULL DEFAULT '{}',
 source_status TEXT NOT NULL DEFAULT 'active'
   CHECK(source_status IN ('active','paused','needs_review','blocked','disabled')),
 monitored BIGINT NOT NULL DEFAULT 1 CHECK(monitored IN (0,1)),
 last_fingerprint TEXT NOT NULL DEFAULT '',
 last_checked_at BIGINT,
 next_check_at BIGINT NOT NULL,
 lease_token TEXT NOT NULL DEFAULT '',
 lease_until BIGINT NOT NULL DEFAULT 0,
 attempts BIGINT NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 12),
 last_http_status BIGINT,
 last_error TEXT NOT NULL DEFAULT '',
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 UNIQUE(workspace_id,quote_item_id,normalized_url)
);
CREATE INDEX IF NOT EXISTS idx_product_sources_due
 ON smetra.product_sources(monitored,next_check_at,lease_until)
 WHERE source_status='active';
CREATE INDEX IF NOT EXISTS idx_product_sources_workspace
 ON smetra.product_sources(workspace_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_sources_quote_item
 ON smetra.product_sources(quote_id,quote_item_id);

CREATE TABLE IF NOT EXISTS smetra.product_price_observations (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 source_id TEXT NOT NULL REFERENCES smetra.product_sources(id) ON DELETE CASCADE,
 fingerprint TEXT NOT NULL,
 product_title TEXT NOT NULL DEFAULT '',
 price_kopecks BIGINT CHECK(price_kopecks IS NULL OR price_kopecks >= 0),
 currency TEXT NOT NULL DEFAULT 'RUB',
 availability TEXT NOT NULL DEFAULT 'unknown'
   CHECK(availability IN ('in_stock','out_of_stock','preorder','backorder','unknown')),
 image_url TEXT NOT NULL DEFAULT '',
 source_url TEXT NOT NULL,
 observed_at BIGINT NOT NULL,
 UNIQUE(source_id,fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_price_observations_history
 ON smetra.product_price_observations(source_id,observed_at DESC);

CREATE TABLE IF NOT EXISTS smetra.cloud_connections (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 provider TEXT NOT NULL CHECK(provider IN ('google_drive','yandex_disk')),
 provider_account_id TEXT NOT NULL DEFAULT '',
 account_label TEXT NOT NULL DEFAULT '',
 access_token_enc TEXT NOT NULL,
 refresh_token_enc TEXT NOT NULL DEFAULT '',
 token_expires_at BIGINT NOT NULL DEFAULT 0,
 scopes TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','reauth_required','revoked','disabled')),
 last_synced_at BIGINT,
 last_error TEXT NOT NULL DEFAULT '',
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 UNIQUE(workspace_id,user_id,provider)
);
CREATE INDEX IF NOT EXISTS idx_cloud_connections_workspace
 ON smetra.cloud_connections(workspace_id,status);

CREATE TABLE IF NOT EXISTS smetra.cloud_oauth_states (
 id TEXT PRIMARY KEY,
 state_hash TEXT NOT NULL UNIQUE,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 provider TEXT NOT NULL CHECK(provider IN ('google_drive','yandex_disk')),
 expires_at BIGINT NOT NULL,
 consumed_at BIGINT,
 created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cloud_oauth_states_expiry
 ON smetra.cloud_oauth_states(expires_at) WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS smetra.cloud_folder_bindings (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 connection_id TEXT NOT NULL REFERENCES smetra.cloud_connections(id) ON DELETE CASCADE,
 folder_id TEXT NOT NULL,
 folder_name TEXT NOT NULL DEFAULT '',
 quote_id TEXT REFERENCES smetra.quotes(id) ON DELETE SET NULL,
 project_id TEXT REFERENCES smetra.projects(id) ON DELETE SET NULL,
 recursive BIGINT NOT NULL DEFAULT 1 CHECK(recursive IN (0,1)),
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','reauth_required','disabled')),
 sync_requested BIGINT NOT NULL DEFAULT 1 CHECK(sync_requested IN (0,1)),
 next_sync_at BIGINT NOT NULL,
 last_synced_at BIGINT,
 last_error TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL REFERENCES smetra.users(id) ON DELETE CASCADE,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 UNIQUE(connection_id,folder_id)
);
CREATE INDEX IF NOT EXISTS idx_cloud_folder_bindings_due
 ON smetra.cloud_folder_bindings(status,sync_requested,next_sync_at);
CREATE INDEX IF NOT EXISTS idx_cloud_folder_bindings_workspace
 ON smetra.cloud_folder_bindings(workspace_id,created_at DESC);

CREATE TABLE IF NOT EXISTS smetra.cloud_files (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 binding_id TEXT NOT NULL REFERENCES smetra.cloud_folder_bindings(id) ON DELETE CASCADE,
 connection_id TEXT NOT NULL REFERENCES smetra.cloud_connections(id) ON DELETE CASCADE,
 provider_file_id TEXT NOT NULL,
 parent_folder_id TEXT NOT NULL DEFAULT '',
 name TEXT NOT NULL,
 mime TEXT NOT NULL DEFAULT 'application/octet-stream',
 size BIGINT NOT NULL DEFAULT 0 CHECK(size>=0),
 modified_at TEXT NOT NULL DEFAULT '',
 source_fingerprint TEXT NOT NULL DEFAULT '',
 web_view_url TEXT NOT NULL DEFAULT '',
 trashed BIGINT NOT NULL DEFAULT 0 CHECK(trashed IN (0,1)),
 processing_status TEXT NOT NULL DEFAULT 'queued'
   CHECK(processing_status IN ('queued','processing','processed','needs_review','ignored','failed')),
 last_error TEXT NOT NULL DEFAULT '',
 first_seen_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 UNIQUE(connection_id,provider_file_id)
);
CREATE INDEX IF NOT EXISTS idx_cloud_files_binding
 ON smetra.cloud_files(binding_id,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cloud_files_processing
 ON smetra.cloud_files(processing_status,updated_at);

CREATE TABLE IF NOT EXISTS smetra.document_processing_jobs (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 cloud_file_id TEXT NOT NULL REFERENCES smetra.cloud_files(id) ON DELETE CASCADE,
 source_fingerprint TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued'
   CHECK(status IN ('queued','running','retry','needs_review','completed','failed','cancelled')),
 progress TEXT NOT NULL DEFAULT 'В очереди',
 extraction TEXT NOT NULL DEFAULT '{}',
 proposal TEXT NOT NULL DEFAULT '{}',
 error TEXT NOT NULL DEFAULT '',
 attempts BIGINT NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
 lease_token TEXT NOT NULL DEFAULT '',
 lease_until BIGINT NOT NULL DEFAULT 0,
 next_attempt_at BIGINT NOT NULL,
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL,
 UNIQUE(cloud_file_id,source_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_document_processing_due
 ON smetra.document_processing_jobs(status,next_attempt_at,lease_until);

CREATE TABLE IF NOT EXISTS smetra.cloud_watch_channels (
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES smetra.workspaces(id) ON DELETE CASCADE,
 connection_id TEXT NOT NULL REFERENCES smetra.cloud_connections(id) ON DELETE CASCADE,
 channel_id TEXT NOT NULL UNIQUE,
 resource_id TEXT NOT NULL DEFAULT '',
 token_hash TEXT NOT NULL,
 page_token TEXT NOT NULL DEFAULT '',
 expires_at BIGINT NOT NULL,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','expired','stopped')),
 created_at BIGINT NOT NULL,
 updated_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cloud_watch_expiry
 ON smetra.cloud_watch_channels(status,expires_at);

-- Keep the tables inaccessible to anon/authenticated REST roles. Runtime access is constrained
-- to the selected workspace and authenticated user through the existing transaction-local scope.
DO $$
DECLARE t TEXT;
BEGIN
 FOREACH t IN ARRAY ARRAY[
  'product_sources','product_price_observations','cloud_connections','cloud_oauth_states',
  'cloud_folder_bindings','cloud_files','document_processing_jobs','cloud_watch_channels'
 ] LOOP
  EXECUTE format('ALTER TABLE smetra.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE smetra.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON smetra.%I FROM PUBLIC,anon,authenticated',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.%I TO smetra_runtime',t);
  EXECUTE format(
   'CREATE POLICY smetra_runtime_scope ON smetra.%I FOR ALL TO smetra_runtime USING (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') AND smetra.runtime_workspace_allowed(workspace_id)) WITH CHECK (workspace_id=nullif(current_setting(''smetra.workspace_id'',true),'''') AND smetra.runtime_workspace_allowed(workspace_id))',
   t
  );
 END LOOP;
END $$;
INSERT INTO smetra.schema_migrations(version,applied_at)
 VALUES(46,EXTRACT(EPOCH FROM NOW())::BIGINT) ON CONFLICT(version) DO NOTHING;
COMMIT;
