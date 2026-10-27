"""Build an empty, loopback-only PostgreSQL fixture from application migrations."""
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
INFRASTRUCTURE = {
    "20261003133128_assistant_job_scheduler.sql",
    "20261003163905_private_worker_queue_permissions.sql",
    "20261003164413_signed_worker_invocations.sql",
    "20261018213000_push_worker_scheduler.sql",
}
PLATFORM = """
CREATE SCHEMA auth;
CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE SQL STABLE AS $$ SELECT '{}'::jsonb $$;
CREATE SCHEMA realtime;
CREATE TABLE realtime.messages(extension TEXT,topic TEXT);
ALTER TABLE realtime.messages ENABLE ROW LEVEL SECURITY;
CREATE FUNCTION realtime.topic() RETURNS text LANGUAGE SQL STABLE AS $$ SELECT ''::text $$;
CREATE FUNCTION realtime.send(jsonb,text,text,boolean) RETURNS void LANGUAGE SQL AS $$ SELECT NULL::void $$;
"""


def validate_target(database_url):
    parameters = conninfo_to_dict(database_url)
    if (urlsplit(database_url).scheme not in ("postgres", "postgresql")
            or parameters.get("host") not in ("127.0.0.1", "localhost", "::1")
            or parameters.get("hostaddr", "127.0.0.1") not in ("127.0.0.1", "::1")
            or not re.fullmatch(r"smetra_test(?:_[a-z0-9_]+)?", parameters.get("dbname", ""))):
        raise ValueError("Use an explicitly named disposable loopback test database")
    return parameters


def prepare(database_url):
    validate_target(database_url)
    with psycopg.connect(database_url, autocommit=True) as con:
        if con.execute("SELECT 1 FROM pg_namespace WHERE nspname='smetra'").fetchone():
            raise ValueError("The fixture database must be empty; nothing was deleted")
        for role in ("anon", "authenticated"):
            if not con.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                con.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        con.execute(PLATFORM)
        for path in sorted((ROOT / "supabase/migrations").glob("*.sql")):
            if path.name in INFRASTRUCTURE:
                continue
            if path.name == "20261018210000_query_performance_indexes.sql":
                con.execute((ROOT / "tests/fixtures/postgres_legacy_baseline.sql").read_text())
                con.execute("SET search_path=smetra,pg_catalog")
                con.execute((ROOT / "backend/migrations/021_assistant_purchase_bonus.sql").read_text())
                con.execute("ALTER TABLE smetra.assistant_jobs ADD COLUMN bonus_grant_id TEXT REFERENCES smetra.assistant_bonus_grants(id)")
                con.execute("SET search_path=public")
            con.execute(path.read_text())
        # Match legacy production grants that predate the checked-in SQL history.
        for table in ("native_web_tickets", "billing_subscriptions"):
            con.execute(sql.SQL("ALTER TABLE smetra.{} ENABLE ROW LEVEL SECURITY").format(sql.Identifier(table)))
        for table, rights in (
            ("assistant_bonus_grants", "SELECT,UPDATE"),
            ("assistant_bonus_usage", "SELECT,INSERT,UPDATE"),
            ("assistant_ad_reward_credits", "SELECT,INSERT,UPDATE"),
        ):
            con.execute(sql.SQL("ALTER TABLE smetra.{} ENABLE ROW LEVEL SECURITY").format(sql.Identifier(table)))
            con.execute(sql.SQL("ALTER TABLE smetra.{} FORCE ROW LEVEL SECURITY").format(sql.Identifier(table)))
            con.execute(sql.SQL("GRANT " + rights + " ON smetra.{} TO smetra_runtime").format(sql.Identifier(table)))
            con.execute(sql.SQL(
                "CREATE POLICY fixture_runtime_user ON smetra.{} FOR ALL TO smetra_runtime "
                "USING(user_id=(select smetra.runtime_user_id())) WITH CHECK(user_id=(select smetra.runtime_user_id()))"
            ).format(sql.Identifier(table)))
        for table in ("quote_followups", "estimate_shares"):
            con.execute(sql.SQL("ALTER TABLE smetra.{} ENABLE ROW LEVEL SECURITY").format(sql.Identifier(table)))
            con.execute(sql.SQL("ALTER TABLE smetra.{} FORCE ROW LEVEL SECURITY").format(sql.Identifier(table)))
            con.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON smetra.{} TO smetra_runtime").format(sql.Identifier(table)))
            con.execute(sql.SQL(
                "CREATE POLICY fixture_workspace ON smetra.{} FOR ALL TO smetra_runtime "
                "USING(workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id)) "
                "WITH CHECK(workspace_id=NULLIF(current_setting('smetra.workspace_id',true),'') AND smetra.runtime_workspace_allowed(workspace_id))"
            ).format(sql.Identifier(table)))
        if not con.execute("SELECT 1 FROM pg_roles WHERE rolname='smetra_ci_runtime'").fetchone():
            con.execute("CREATE ROLE smetra_ci_runtime LOGIN PASSWORD 'fixture-only' IN ROLE smetra_runtime")
        version = con.execute("SELECT max(version) FROM smetra.schema_migrations").fetchone()[0]
    return {"ok": True, "schema_version": version, "excluded": sorted(INFRASTRUCTURE)}


if __name__ == "__main__":
    import json
    print(json.dumps(prepare(os.environ["SMETRA_TEST_ADMIN_URL"])))
