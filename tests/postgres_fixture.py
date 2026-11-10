"""Prepare the real migration chain in a fresh, disposable loopback PostgreSQL.

Hosted scheduler extensions are deliberately omitted. Only the Realtime/Auth
interfaces used by migration DDL are stubbed; API, RLS, tables and money are real.
"""
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

import psycopg

ROOT = Path(__file__).resolve().parents[1]
HOSTED_ONLY = frozenset({
    "20261003133128_assistant_job_scheduler.sql",
    "20261018213000_push_worker_scheduler.sql",
})


def prepare(database_url, runtime_role="smetra_ci_runtime", runtime_password="fixture-only"):
    import re
    if urlsplit(database_url).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("The test database must be on loopback")
    if not re.fullmatch(r"smetra_[a-z_]+", runtime_role):
        raise ValueError("Invalid disposable runtime role")
    with psycopg.connect(database_url, autocommit=True) as con:
        if con.execute("SELECT to_regnamespace('smetra')").fetchone()[0] is not None:
            raise RuntimeError("Use a fresh disposable database; an existing schema will not be changed")
        for role in ("anon", "authenticated", "service_role"):
            if not con.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                con.execute(psycopg.sql.SQL("CREATE ROLE {} NOLOGIN").format(psycopg.sql.Identifier(role)))
        con.execute("CREATE SCHEMA auth; CREATE SCHEMA realtime; CREATE SCHEMA net")
        con.execute("CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql AS $$ SELECT '{}'::jsonb $$")
        con.execute("CREATE TABLE realtime.messages(id bigint,extension text); ALTER TABLE realtime.messages ENABLE ROW LEVEL SECURITY")
        con.execute("CREATE FUNCTION realtime.topic() RETURNS text LANGUAGE sql AS $$ SELECT ''::text $$")
        con.execute("CREATE FUNCTION realtime.send(jsonb,text,text,boolean) RETURNS void LANGUAGE plpgsql AS $$ BEGIN RETURN; END $$")
        for migration in sorted((ROOT / "supabase/migrations").glob("*.sql")):
            if migration.name not in HOSTED_ONLY:
                con.execute(migration.read_text(encoding="utf-8"))
        if not con.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (runtime_role,)).fetchone():
            con.execute(psycopg.sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS INHERIT PASSWORD {} IN ROLE smetra_runtime").format(
                psycopg.sql.Identifier(runtime_role), psycopg.sql.Literal(runtime_password),
            ))
        return con.execute("SELECT max(version) FROM smetra.schema_migrations").fetchone()[0]


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    print("Prepared isolated PostgreSQL schema version", prepare(os.environ["SMETRA_TEST_ADMIN_URL"]))
