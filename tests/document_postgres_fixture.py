"""Restore legacy cloud baseline for disposable loopback PostgreSQL tests.

Production already has these objects. The versioned cloud migration chain omits
the old purchase-bonus baseline that is present in the SQLite migrations. Never
run fixture DDL against a hosted database or application DATABASE_URL.
"""

from pathlib import Path
from urllib.parse import urlsplit

import psycopg

from backend.postgres import translate


def prepare(admin_url):
    if urlsplit(admin_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        return
    with psycopg.connect(admin_url) as con:
        source = (Path(__file__).resolve().parents[1] / 'backend/migrations/021_assistant_purchase_bonus.sql').read_text(encoding='utf-8')
        for statement in source.split(';'):
            if statement.strip():
                con.execute(translate(statement.replace('INTEGER', 'BIGINT'), 'smetra'))
        con.execute('ALTER TABLE smetra.assistant_jobs ADD COLUMN IF NOT EXISTS bonus_grant_id text')
        # Match the verified production grants and user-scoped RLS. No wallet
        # contents, credits, limits or application data are fabricated.
        for table, grant in (
            ('assistant_bonus_grants', 'SELECT,UPDATE'),
            ('assistant_bonus_usage', 'SELECT,INSERT,UPDATE'),
            ('assistant_ad_reward_credits', 'SELECT,INSERT,UPDATE'),
        ):
            con.execute(f'ALTER TABLE smetra.{table} ENABLE ROW LEVEL SECURITY')
            con.execute(f'ALTER TABLE smetra.{table} FORCE ROW LEVEL SECURITY')
            con.execute(f'REVOKE ALL ON smetra.{table} FROM PUBLIC,anon,authenticated')
            con.execute(f'GRANT {grant} ON smetra.{table} TO smetra_runtime')
            if not con.execute('SELECT 1 FROM pg_policies WHERE schemaname=%s AND tablename=%s AND roles @> ARRAY[%s]::name[]',
                               ('smetra', table, 'smetra_runtime')).fetchone():
                con.execute(f'CREATE POLICY document_fixture_owner ON smetra.{table} FOR ALL TO smetra_runtime '
                            'USING(user_id=(SELECT smetra.runtime_user_id())) '
                            'WITH CHECK(user_id=(SELECT smetra.runtime_user_id()))')
