-- Reuse the authenticated worker secret already provisioned in Supabase Vault.
-- Only an expiring, nonce-bound HMAC signature is sent through pg_net.
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

CREATE OR REPLACE FUNCTION smetra.wake_push_worker()
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  worker_secret TEXT;
  request_id BIGINT;
  moment TEXT;
  nonce TEXT;
  signature TEXT;
  now_epoch BIGINT;
BEGIN
  now_epoch := extract(epoch FROM now())::BIGINT;
  IF NOT EXISTS (
    SELECT 1 FROM smetra.push_outbox
    WHERE sent_at IS NULL
      AND next_attempt_at <= now_epoch
      AND lease_until < now_epoch
  ) THEN
    RETURN NULL;
  END IF;

  SELECT decrypted_secret INTO worker_secret
  FROM vault.decrypted_secrets
  WHERE name='smetra_assistant_worker_secret'
  LIMIT 1;
  IF worker_secret IS NULL OR length(worker_secret)<32 THEN
    RETURN NULL;
  END IF;

  moment := now_epoch::TEXT;
  nonce := replace(gen_random_uuid()::TEXT,'-','');
  signature := encode(
    extensions.hmac(
      'smetra-push-worker:v1:' || moment || ':' || nonce,
      worker_secret,
      'sha256'
    ),
    'hex'
  );

  SELECT net.http_get(
    url := 'https://smetra.vercel.app/api/cron/push',
    headers := jsonb_build_object(
      'Authorization',
      'Bearer v1.' || moment || '.' || nonce || '.' || signature
    ),
    timeout_milliseconds := 120000
  ) INTO request_id;
  RETURN request_id;
END;
$$;

REVOKE ALL ON FUNCTION smetra.wake_push_worker() FROM PUBLIC,anon,authenticated,smetra_runtime;

SELECT cron.unschedule(jobid)
FROM cron.job
WHERE jobname='smetra-push-worker';
SELECT cron.schedule(
  'smetra-push-worker',
  '* * * * *',
  'SELECT smetra.wake_push_worker()'
);

INSERT INTO smetra.schema_migrations(version,applied_at)
VALUES(33,extract(epoch FROM now())::BIGINT) ON CONFLICT DO NOTHING;
