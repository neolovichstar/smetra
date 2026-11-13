"""Optional real-PostgreSQL isolation test; set both SMETRA_TEST_*_URL variables."""

import os
import secrets
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import psycopg

from backend.business import Service
from backend.postgres import Connection


@unittest.skipUnless(
    os.getenv("SMETRA_TEST_ADMIN_URL") and os.getenv("SMETRA_TEST_RUNTIME_URL"),
    "requires a disposable PostgreSQL with migration 7 and runtime login role",
)
class RuntimeRlsTests(unittest.TestCase):
    def test_workspace_overview_hides_personal_file_events_on_runtime_connection(self):
        owner, colleague, workspace = (str(uuid.uuid4()) for _ in range(3))
        session = secrets.token_hex(32)
        moment = int(time.time())
        with psycopg.connect(os.environ["SMETRA_TEST_ADMIN_URL"], autocommit=True) as admin:
            try:
                for user in (owner, colleague):
                    admin.execute(
                        "INSERT INTO smetra.users(id,email,password_hash,name,created_at) "
                        "VALUES(%s,%s,'unused','Activity QA',%s)",
                        (user, user + "@test.invalid", moment),
                    )
                admin.execute(
                    "INSERT INTO smetra.workspaces(id,owner_id,name,created_at) VALUES(%s,%s,'Activity QA',%s)",
                    (workspace, owner, moment),
                )
                admin.execute(
                    "INSERT INTO smetra.workspace_members(workspace_id,user_id,role) "
                    "VALUES(%s,%s,'owner'),(%s,%s,'member')",
                    (workspace, owner, workspace, colleague),
                )
                admin.execute(
                    "INSERT INTO smetra.sessions(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
                    (str(uuid.uuid4()), owner, session, moment + 3600),
                )
                for kind, detail in (("personal_file", "private.txt"), ("file", "old-private.txt"),
                                     ("workspace_file", "shared.txt")):
                    admin.execute(
                        "INSERT INTO smetra.activity(id,workspace_id,actor_id,entity_type,entity_id,action,detail,created_at) "
                        "VALUES(%s,%s,%s,%s,%s,'File event',%s,%s)",
                        (str(uuid.uuid4()), workspace, colleague, kind, str(uuid.uuid4()), detail, moment),
                    )
                with patch.dict(os.environ, RUNTIME_DATABASE_URL=os.environ["SMETRA_TEST_RUNTIME_URL"],
                                SMETRA_LOCAL_POSTGRES="1"):
                    con = Connection(runtime=True)
                    try:
                        con.scope(session, workspace)
                        service = Service(SimpleNamespace(), con, "https://example.test")
                        service.wid, service.user, service.role = workspace, {"id": owner}, "owner"
                        status, result = service.overview()
                        self.assertEqual(status, 200)
                        self.assertEqual([item["detail"] for item in result["activity"]], ["shared.txt"])
                    finally:
                        con.close()
            finally:
                admin.execute("DELETE FROM smetra.workspaces WHERE id=%s", (workspace,))
                admin.execute("DELETE FROM smetra.users WHERE id IN (%s,%s)", (owner, colleague))

    def test_session_scoped_read_write_and_grants(self):
        admin_url = os.environ["SMETRA_TEST_ADMIN_URL"]
        runtime_url = os.environ["SMETRA_TEST_RUNTIME_URL"]
        owner_ids = [str(uuid.uuid4()) for _ in range(2)]
        workspace_ids = [str(uuid.uuid4()) for _ in range(2)]
        client_ids = [str(uuid.uuid4()) for _ in range(2)]
        session_hash = secrets.token_hex(32)
        with psycopg.connect(admin_url, autocommit=True) as admin:
            self.assertTrue(admin.execute(
                "SELECT 1 FROM smetra.schema_migrations WHERE version=7"
            ).fetchone())
            try:
                for index in range(2):
                    admin.execute(
                        "INSERT INTO smetra.users(id,email,password_hash,name,created_at) "
                        "VALUES(%s,%s,'unused','RLS QA',%s)",
                        (owner_ids[index], f"rls-{owner_ids[index]}@test.invalid", int(time.time())),
                    )
                    admin.execute(
                        "INSERT INTO smetra.workspaces(id,owner_id,name,created_at) VALUES(%s,%s,'RLS QA',%s)",
                        (workspace_ids[index], owner_ids[index], int(time.time())),
                    )
                    admin.execute(
                        "INSERT INTO smetra.workspace_members(workspace_id,user_id,role) "
                        "VALUES(%s,%s,'owner')", (workspace_ids[index], owner_ids[index]),
                    )
                    admin.execute(
                        "INSERT INTO smetra.clients(id,workspace_id,name,created_at,updated_at) "
                        "VALUES(%s,%s,'Private',0,0)", (client_ids[index], workspace_ids[index]),
                    )
                admin.execute(
                    "INSERT INTO smetra.sessions(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
                    (str(uuid.uuid4()), owner_ids[0], session_hash, int(time.time()) + 3600),
                )
                with psycopg.connect(runtime_url, autocommit=True) as con:
                    self.assertEqual(con.execute(
                        "SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user"
                    ).fetchone(), (False,))
                    self.assertEqual(con.execute(
                        "SELECT count(*) FROM smetra.clients"
                    ).fetchone(), (0,))
                    self.assertFalse(con.execute(
                        "SELECT has_table_privilege(current_user,'smetra.payments','SELECT')"
                    ).fetchone()[0])
                    con.execute("BEGIN")
                    con.execute(
                        "SELECT set_config('smetra.session_hash',%s,true),"
                        "set_config('smetra.workspace_id',%s,true)",
                        (session_hash, workspace_ids[0]),
                    )
                    self.assertTrue(con.execute(
                        "SELECT id FROM smetra.clients WHERE id=%s", (client_ids[0],)
                    ).fetchone())
                    self.assertIsNone(con.execute(
                        "SELECT id FROM smetra.clients WHERE id=%s", (client_ids[1],)
                    ).fetchone())
                    self.assertIsNone(con.execute(
                        "SELECT id FROM smetra.users WHERE id=%s", (owner_ids[1],)
                    ).fetchone())
                    con.execute("SAVEPOINT denied")
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        con.execute(
                            "INSERT INTO smetra.clients(id,workspace_id,name,created_at,updated_at) "
                            "VALUES(%s,%s,'Forbidden',0,0)",
                            (str(uuid.uuid4()), workspace_ids[1]),
                        )
                    con.execute("ROLLBACK TO SAVEPOINT denied")
                    # Token quotas switched from assistant:month to
                    # assistant:tokens. The runtime role must update only its
                    # own current-month counter, not another user's quota.
                    migrated = admin.execute(
                        "SELECT 1 FROM smetra.schema_migrations WHERE version=58"
                    ).fetchone()
                    if migrated:
                        from backend.ai_tokens import month_key

                        own_key = month_key(owner_ids[0])
                        foreign_key = month_key(owner_ids[1])
                        value = con.execute(
                            "INSERT INTO smetra.rate_limits(key,count,started) "
                            "VALUES(%s,1,%s) ON CONFLICT(key) "
                            "DO UPDATE SET count=smetra.rate_limits.count+1 "
                            "RETURNING count",
                            (own_key, int(time.time())),
                        ).fetchone()
                        self.assertEqual(value[0], 1)
                        con.execute("SAVEPOINT denied_token_counter")
                        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                            con.execute(
                                "INSERT INTO smetra.rate_limits(key,count,started) VALUES(%s,1,%s)",
                                (foreign_key, int(time.time())),
                            )
                        con.execute("ROLLBACK TO SAVEPOINT denied_token_counter")
                    con.execute("SELECT set_config('smetra.workspace_id',%s,true)", (workspace_ids[1],))
                    self.assertEqual(con.execute(
                        "SELECT count(*) FROM smetra.clients"
                    ).fetchone(), (0,))
                    con.execute("ROLLBACK")
            finally:
                for workspace_id in workspace_ids:
                    admin.execute("DELETE FROM smetra.workspaces WHERE id=%s", (workspace_id,))
                for user_id in owner_ids:
                    admin.execute("DELETE FROM smetra.users WHERE id=%s", (user_id,))
