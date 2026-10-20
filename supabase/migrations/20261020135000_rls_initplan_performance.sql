BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- Cache request context once per statement instead of re-reading it per row.
-- runtime_workspace_allowed(workspace_id) is intentionally left unwrapped:
-- its argument depends on the current row and must be evaluated per row.
DO $migration$
DECLARE
    p record;
    new_qual text;
    new_check text;
    command text;
BEGIN
    FOR p IN
        SELECT schemaname, tablename, policyname, qual, with_check
        FROM pg_policies
        WHERE schemaname = 'smetra'
        ORDER BY tablename, policyname
    LOOP
        new_qual := p.qual;
        new_check := p.with_check;

        IF new_qual IS NOT NULL THEN
            new_qual := replace(
                new_qual,
                $needle$NULLIF(current_setting('smetra.workspace_id'::text, true), ''::text)$needle$,
                $replacement$(SELECT NULLIF(current_setting('smetra.workspace_id'::text, true), ''::text))$replacement$
            );
            IF position('smetra.runtime_user_id()' IN new_qual) > 0
               AND position('( SELECT smetra.runtime_user_id() AS runtime_user_id)' IN new_qual) = 0
               AND position('(SELECT smetra.runtime_user_id())' IN new_qual) = 0 THEN
                new_qual := replace(
                    new_qual,
                    'smetra.runtime_user_id()',
                    '(SELECT smetra.runtime_user_id())'
                );
            END IF;
        END IF;

        IF new_check IS NOT NULL THEN
            new_check := replace(
                new_check,
                $needle$NULLIF(current_setting('smetra.workspace_id'::text, true), ''::text)$needle$,
                $replacement$(SELECT NULLIF(current_setting('smetra.workspace_id'::text, true), ''::text))$replacement$
            );
            IF position('smetra.runtime_user_id()' IN new_check) > 0
               AND position('( SELECT smetra.runtime_user_id() AS runtime_user_id)' IN new_check) = 0
               AND position('(SELECT smetra.runtime_user_id())' IN new_check) = 0 THEN
                new_check := replace(
                    new_check,
                    'smetra.runtime_user_id()',
                    '(SELECT smetra.runtime_user_id())'
                );
            END IF;
        END IF;

        IF new_qual IS DISTINCT FROM p.qual
           OR new_check IS DISTINCT FROM p.with_check THEN
            command := format(
                'ALTER POLICY %I ON %I.%I',
                p.policyname, p.schemaname, p.tablename
            );
            IF new_qual IS NOT NULL THEN
                command := command || format(' USING (%s)', new_qual);
            END IF;
            IF new_check IS NOT NULL THEN
                command := command || format(' WITH CHECK (%s)', new_check);
            END IF;
            EXECUTE command;
        END IF;
    END LOOP;
END
$migration$;

INSERT INTO smetra.schema_migrations(version, applied_at)
VALUES (38, extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
