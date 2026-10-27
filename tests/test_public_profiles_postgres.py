"""Run against a disposable PostgreSQL to verify private-schema policies and bytea."""

import base64
import io
import os
import secrets
import time
import unittest
import uuid
from unittest.mock import patch

import psycopg
from PIL import Image

from backend.postgres import Connection
from backend.public_profiles import (
    save_profile,
    search,
    get_public,
    own_profile,
    store_avatar,
)


@unittest.skipUnless(
    os.getenv("SMETRA_TEST_ADMIN_URL") and os.getenv("SMETRA_TEST_RUNTIME_URL"),
    "requires disposable PostgreSQL and limited runtime role",
)
class PublicProfilePostgresTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "DATABASE_URL": os.environ["SMETRA_TEST_ADMIN_URL"],
                "RUNTIME_DATABASE_URL": os.environ["SMETRA_TEST_RUNTIME_URL"],
                "SMETRA_LOCAL_POSTGRES": "1",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.users = []
        self.workspaces = []
        self.sessions = []
        self.admin = Connection()
        self.addCleanup(self.admin.close)
        self.addCleanup(self.clean)
        for i in range(2):
            user_id = str(uuid.uuid4())
            wid = str(uuid.uuid4())
            session = secrets.token_hex(32)
            self.users.append(
                {
                    "id": user_id,
                    "name": "Анна Иванова",
                    "avatar_id": "",
                    "email_verified_at": int(time.time()),
                }
            )
            self.workspaces.append(wid)
            self.sessions.append(session)
            self.admin.execute(
                "INSERT INTO users(id,email,password_hash,name,created_at) VALUES(?,?,'unused','Anna',?)",
                (user_id, user_id + "@test.invalid", int(time.time())),
            )
            self.admin.execute(
                "INSERT INTO workspaces(id,owner_id,name,created_at) VALUES(?,?,'Profiles QA',?)",
                (wid, user_id, int(time.time())),
            )
            self.admin.execute(
                "INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'owner')",
                (wid, user_id),
            )
            self.admin.execute(
                "INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                (str(uuid.uuid4()), user_id, session, int(time.time()) + 3600),
            )
            save_profile(
                self.admin,
                self.users[i],
                {
                    "revision": 0,
                    "display_name": "Анна Иванова",
                    "handle": "qa_" + uuid.uuid4().hex[:14],
                    "published": True,
                },
            )

    def clean(self):
        for wid in self.workspaces:
            self.admin.execute(
                "DELETE FROM workspace_members WHERE workspace_id=?", (wid,)
            )
            self.admin.execute("DELETE FROM workspaces WHERE id=?", (wid,))
        for user in self.users:
            self.admin.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            self.admin.execute("DELETE FROM users WHERE id=?", (user["id"],))

    def runtime(self, index=0):
        con = Connection(runtime=True)
        con.scope(self.sessions[index], self.workspaces[index])
        return con

    def test_public_projection_unicode_search_and_real_bytea(self):
        p = own_profile(self.admin, self.users[0])
        found = search(self.admin, "ИВАН")
        self.assertIn(p["public_id"], [r["public_id"] for r in found])
        self.assertEqual(get_public(self.admin, p["handle"])["name"], "Анна Иванова")
        image = Image.new("RGB", (48, 32), "#8ba38e")
        out = io.BytesIO()
        image.save(out, "PNG")
        url = store_avatar(
            self.admin, self.users[0], base64.b64encode(out.getvalue()).decode()
        )
        row = self.admin.execute(
            "SELECT content,content_hash FROM profile_avatars WHERE user_id=?",
            (self.users[0]["id"],),
        ).fetchone()
        self.assertTrue(bytes(row["content"]).startswith(b"RIFF"))
        self.assertIn(row["content_hash"], url)

    def test_runtime_owns_only_its_profile_terms_and_avatar(self):
        for i, user in enumerate(self.users):
            self.admin.execute(
                "INSERT INTO profile_avatars VALUES(?,'fixture',?,?)",
                (user["id"], b"private", int(time.time())),
            )
        runtime = self.runtime()
        try:
            for table in ("public_profiles", "profile_search_terms", "profile_avatars"):
                rows = runtime.execute("SELECT user_id FROM " + table).fetchall()
                self.assertTrue(rows)
                self.assertEqual({r["user_id"] for r in rows}, {self.users[0]["id"]})
            saved = save_profile(
                runtime,
                self.users[0],
                {"revision": 1, "bio": "Мой открытый профиль", "published": False},
            )
            self.assertFalse(saved["published"])
            self.assertFalse(
                runtime.execute("SELECT 1 FROM profile_search_terms").fetchall()
            )
            result = runtime.execute(
                "UPDATE public_profiles SET bio='stolen' WHERE user_id=?",
                (self.users[1]["id"],),
            )
            self.assertEqual(result.rowcount, 0)
            runtime.finish(True)
        finally:
            runtime.close()
        for table in ("public_profiles", "profile_search_terms", "profile_avatars"):
            row = self.admin.raw.execute(
                "SELECT has_table_privilege('anon',%s,'SELECT') AS anon_allowed,has_table_privilege('authenticated',%s,'SELECT') AS authenticated_allowed",
                ("smetra." + table, "smetra." + table),
            ).fetchone()
            self.assertFalse(row[0])
            self.assertFalse(row[1])
        runtime = self.runtime()
        try:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                runtime.execute(
                    "INSERT INTO profile_avatars VALUES(?,'stolen',?,0) ON CONFLICT(user_id) DO UPDATE SET content=excluded.content",
                    (self.users[1]["id"], b"attack"),
                )
            runtime.finish(False)
        finally:
            runtime.close()
