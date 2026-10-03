-- Hosted pg_net grants are platform-owned. Never put a persistent bearer key
-- into its request queue; sign a narrowly scoped, expiring, one-use invocation.
CREATE OR REPLACE FUNCTION smetra.wake_assistant_worker()
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE worker_secret text; request_id bigint; moment text; nonce text; signature text;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM smetra.assistant_jobs
    WHERE (status IN ('queued','retry') AND next_attempt_at <= extract(epoch FROM now())::bigint)
      OR (status='running' AND lease_until <= extract(epoch FROM now())::bigint)
  ) THEN RETURN NULL; END IF;
  SELECT decrypted_secret INTO worker_secret FROM vault.decrypted_secrets
    WHERE name='smetra_assistant_worker_secret' LIMIT 1;
  IF worker_secret IS NULL OR length(worker_secret)<32 THEN RETURN NULL; END IF;
  moment := extract(epoch FROM now())::bigint::text;
  nonce := replace(gen_random_uuid()::text,'-','');
  signature := encode(extensions.hmac('smetra-assistant-worker:v1:' || moment || ':' || nonce, worker_secret, 'sha256'),'hex');
  SELECT net.http_get(
    url := 'https://smetra.vercel.app/api/cron/assistant',
    headers := jsonb_build_object('Authorization','Bearer v1.' || moment || '.' || nonce || '.' || signature),
    timeout_milliseconds := 120000
  ) INTO request_id;
  RETURN request_id;
END;
$$;
REVOKE ALL ON FUNCTION smetra.wake_assistant_worker() FROM PUBLIC,anon,authenticated,smetra_runtime;
