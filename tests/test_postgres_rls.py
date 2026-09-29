"""Optional real-PostgreSQL isolation test; set both SMETRA_TEST_*_URL variables."""

import os
import secrets
import time
import unittest
import uuid

import psycopg


@unittest.skipUnless(
    os.getenv("SMETRA_TEST_ADMIN_URL") and os.getenv("SMETRA_TEST_RUNTIME_URL"),
    "requires a disposable PostgreSQL with migration 7 and runtime login role",
)
class RuntimeRlsTests(unittest.TestCase):
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
