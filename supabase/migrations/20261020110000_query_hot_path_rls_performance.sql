BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- Composite indexes for the dashboard's actual workspace/state/date filters.
CREATE INDEX IF NOT EXISTS idx_events_user_name
    ON smetra.events(user_id, name);
CREATE INDEX IF NOT EXISTS idx_quotes_workspace_approval_updated
    ON smetra.quotes(workspace_id, approval_state, updated_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_quotes_workspace_approved_at
    ON smetra.quotes(workspace_id, approved_at DESC)
    WHERE approved_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quotes_workspace_sent_at
    ON smetra.quotes(workspace_id, sent_at)
    WHERE sent_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_quotes_workspace_first_viewed
    ON smetra.quotes(workspace_id, first_viewed_at DESC)
    WHERE first_viewed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_workspace_due_status
    ON smetra.projects(workspace_id, due_date, status);
CREATE INDEX IF NOT EXISTS idx_project_payments_workspace_project_created
    ON smetra.project_payments(workspace_id, project_id, created_at DESC);

-- Make stable request-context reads initplans instead of re-evaluating them
-- for every candidate row. Keep correlated checks correlated unless the policy
-- already constrains workspace_id to the transaction-local workspace.
DO $$
DECLARE
    policy_row record;
    new_using text;
    new_check text;
    alter_sql text;
BEGIN
    FOR policy_row IN
        SELECT schemaname, tablename, policyname, qual, with_check
        FROM pg_policies
        WHERE schemaname = 'smetra'
          AND policyname LIKE 'smetra_runtime%'
          AND (
              coalesce(qual, '') LIKE '%current_setting(%'
              OR coalesce(with_check, '') LIKE '%current_setting(%'
              OR coalesce(qual, '') LIKE '%smetra.runtime_user_id()%'
              OR coalesce(with_check, '') LIKE '%smetra.runtime_user_id()%'
          )
    LOOP
        new_using := policy_row.qual;
        new_check := policy_row.with_check;

        IF new_using IS NOT NULL
           AND strpos(new_using, 'workspace_id = NULLIF(current_setting(''smetra.workspace_id''::text, true),') > 0 THEN
            new_using := replace(
                new_using,
                'smetra.runtime_workspace_allowed(workspace_id)',
                '( SELECT smetra.runtime_workspace_allowed(NULLIF(current_setting(''smetra.workspace_id''::text, true), ''''::text)))'
            );
        END IF;
        IF new_check IS NOT NULL
           AND strpos(new_check, 'workspace_id = NULLIF(current_setting(''smetra.workspace_id''::text, true),') > 0 THEN
            new_check := replace(
                new_check,
                'smetra.runtime_workspace_allowed(workspace_id)',
                '( SELECT smetra.runtime_workspace_allowed(NULLIF(current_setting(''smetra.workspace_id''::text, true), ''''::text)))'
            );
        END IF;

        IF new_using IS NOT NULL THEN
            new_using := replace(
                new_using,
                'current_setting(''smetra.workspace_id''::text, true)',
                '( SELECT current_setting(''smetra.workspace_id''::text, true))'
            );
            new_using := replace(
                new_using,
                'current_setting(''smetra.session_hash''::text, true)',
                '( SELECT current_setting(''smetra.session_hash''::text, true))'
            );
            new_using := replace(new_using, 'smetra.runtime_user_id()', '( SELECT smetra.runtime_user_id())');
        END IF;
        IF new_check IS NOT NULL THEN
            new_check := replace(
                new_check,
                'current_setting(''smetra.workspace_id''::text, true)',
                '( SELECT current_setting(''smetra.workspace_id''::text, true))'
            );
            new_check := replace(
                new_check,
                'current_setting(''smetra.session_hash''::text, true)',
                '( SELECT current_setting(''smetra.session_hash''::text, true))'
            );
            new_check := replace(new_check, 'smetra.runtime_user_id()', '( SELECT smetra.runtime_user_id())');
        END IF;

        IF new_using IS DISTINCT FROM policy_row.qual
           OR new_check IS DISTINCT FROM policy_row.with_check THEN
            alter_sql := format(
                'ALTER POLICY %I ON %I.%I',
                policy_row.policyname,
                policy_row.schemaname,
                policy_row.tablename
            );
            IF policy_row.qual IS NOT NULL THEN
                alter_sql := alter_sql || format(' USING (%s)', new_using);
            END IF;
            IF policy_row.with_check IS NOT NULL THEN
                alter_sql := alter_sql || format(' WITH CHECK (%s)', new_check);
            END IF;
            EXECUTE alter_sql;
        END IF;
    END LOOP;
END
$$;

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (38, extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
