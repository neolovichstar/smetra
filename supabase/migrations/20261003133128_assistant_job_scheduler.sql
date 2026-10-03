-- Only wake Vercel when work is due. The credential is provisioned separately
-- in Vault and the server environment; it never appears in migration source.
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

CREATE OR REPLACE FUNCTION smetra.wake_assistant_worker()
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE worker_secret text; request_id bigint;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM smetra.assistant_jobs
    WHERE (status IN ('queued','retry') AND next_attempt_at <= extract(epoch FROM now())::bigint)
      OR (status='running' AND lease_until <= extract(epoch FROM now())::bigint)
  ) THEN RETURN NULL; END IF;
  SELECT decrypted_secret INTO worker_secret FROM vault.decrypted_secrets
    WHERE name='smetra_assistant_worker_secret' LIMIT 1;
  IF worker_secret IS NULL OR length(worker_secret)<32 THEN RETURN NULL; END IF;
  SELECT net.http_get(
    url := 'https://smetra.vercel.app/api/cron/assistant',
    headers := jsonb_build_object('Authorization','Bearer ' || worker_secret),
    timeout_milliseconds := 120000
  ) INTO request_id;
  RETURN request_id;
END;
$$;
REVOKE ALL ON FUNCTION smetra.wake_assistant_worker() FROM PUBLIC,anon,authenticated,smetra_runtime;
SELECT cron.schedule('smetra-assistant-worker','* * * * *','SELECT smetra.wake_assistant_worker()');
SELECT cron.schedule('smetra-assistant-maintenance','35 3 * * *',$$
  DELETE FROM smetra.assistant_jobs WHERE status IN ('completed','failed','cancelled')
    AND updated_at < extract(epoch FROM now()-interval '30 days')::bigint;
  DELETE FROM cron.job_run_details WHERE jobid IN (
    SELECT jobid FROM cron.job WHERE jobname IN ('smetra-assistant-worker','smetra-assistant-maintenance')
  ) AND end_time < now()-interval '7 days';
$$);
