BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- Put current_setting itself behind a scalar subquery so PostgreSQL can
-- evaluate request-scoped context as an InitPlan, once per SQL statement.
-- Leave NULLIF outside the subquery and preserve all membership predicates.
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
                $old$( SELECT NULLIF(current_setting('smetra.workspace_id'::text, true), ''::text) AS "nullif")$old$,
                $new$NULLIF(( SELECT current_setting('smetra.workspace_id'::text, true) AS current_setting), ''::text)$new$
            );
        END IF;
        IF new_check IS NOT NULL THEN
            new_check := replace(
                new_check,
                $old$( SELECT NULLIF(current_setting('smetra.workspace_id'::text, true), ''::text) AS "nullif")$old$,
                $new$NULLIF(( SELECT current_setting('smetra.workspace_id'::text, true) AS current_setting), ''::text)$new$
            );
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
VALUES (39, extract(epoch FROM now())::BIGINT)
ON CONFLICT DO NOTHING;
COMMIT;
