BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='30s';

-- Hoist only the row-independent workspace setting. Keep membership checks,
-- role lists, command kinds and row-dependent predicates exactly as they are.
DO $migration$
DECLARE
    p record;
    new_qual text;
    new_check text;
    command text;
    old_context constant text := $old$NULLIF(current_setting('smetra.workspace_id'::text, true), ''::text)$old$;
    new_context constant text := $new$NULLIF((SELECT current_setting('smetra.workspace_id'::text, true)), ''::text)$new$;
BEGIN
    FOR p IN
        SELECT schemaname,tablename,policyname,qual,with_check
        FROM pg_policies
        WHERE schemaname='smetra'
          AND tablename IN (
              'product_sources','product_price_observations','cloud_connections',
              'cloud_oauth_states','cloud_folder_bindings','cloud_files',
              'document_processing_jobs','cloud_watch_channels',
              'object_chat_threads','object_chat_messages','project_cash_risks',
              'estimate_shares','outbox_events','estimate_share_responses'
          )
    LOOP
        new_qual := replace(p.qual,old_context,new_context);
        new_check := replace(p.with_check,old_context,new_context);
        IF new_qual IS DISTINCT FROM p.qual OR new_check IS DISTINCT FROM p.with_check THEN
            -- The exact substitution must be reversible: no other condition changes.
            IF replace(new_qual,new_context,old_context) IS DISTINCT FROM p.qual
               OR replace(new_check,new_context,old_context) IS DISTINCT FROM p.with_check THEN
                RAISE EXCEPTION 'Unexpected policy transformation';
            END IF;
            command := format('ALTER POLICY %I ON %I.%I',p.policyname,p.schemaname,p.tablename);
            IF new_qual IS NOT NULL THEN
                command := command || format(' USING (%s)',new_qual);
            END IF;
            IF new_check IS NOT NULL THEN
                command := command || format(' WITH CHECK (%s)',new_check);
            END IF;
            EXECUTE command;
        END IF;
    END LOOP;
END
$migration$;
COMMIT;
