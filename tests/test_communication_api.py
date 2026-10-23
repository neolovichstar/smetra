import hashlib
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import backend.app as app
import backend.community as community


class CommunicationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_db_path = app.DB_PATH
        app.DB_PATH = Path(cls.temp.name) / "communication-api.sqlite3"
        app.migrate()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_address[1])
        cls.admin_token, cls.admin_id = cls.register("Администратор", "admin-comms@example.test", "admin")
        cls.alice_token, cls.alice_id = cls.register("Алиса", "alice-comms@example.test", "user")
        cls.bob_token, cls.bob_id = cls.register("Борис", "bob-comms@example.test", "user")

    @classmethod
    def register(cls, name, email, role):
        token, user_id = app.secrets.token_urlsafe(32), app.uid()
        with app.db() as con:
            con.execute(
                "INSERT INTO users(id,email,password_hash,name,role,created_at,email_verified_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (user_id, email, app.hash_password("safe long test password"), name, role, app.now(), app.now()),
            )
            con.execute(
                "INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                (app.uid(), user_id, hashlib.sha256(token.encode()).hexdigest(), app.now() + 3600),
            )
            app.business.ensure_workspace(con, {"id": user_id, "name": name})
        return token, user_id

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        app.DB_PATH = cls.original_db_path
        cls.temp.cleanup()

    def request(self, path, method="GET", data=None, token=None):
        payload = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(self.base + path, payload, headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            return response.code, json.load(response)

    def test_public_id_directory_and_direct_chat_membership(self):
        status, identity = self.request("/api/profile/id", token=self.alice_token)
        self.assertEqual(status, 200)
        self.assertEqual(identity["public_id"], community.make_public_id(self.alice_id))

        status, found = self.request(
            "/api/profile/directory?q=" + identity_for(self.bob_id),
            token=self.alice_token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(found["user"]["id"], self.bob_id)

        status, result = self.request(
            "/api/profile/chats", "POST",
            {"public_id": community.make_public_id(self.bob_id)},
            self.alice_token,
        )
        self.assertEqual(status, 200)
        chat_id = result["chat"]["id"]

        status, sent = self.request(
            f"/api/profile/chats/{chat_id}/messages", "POST",
            {"message": "Привет, обсудим объект?"},
            self.alice_token,
        )
        self.assertEqual(status, 201)
        self.assertEqual(sent["message"]["body"], "Привет, обсудим объект?")

        status, messages = self.request(
            f"/api/profile/chats/{chat_id}/messages", token=self.bob_token
        )
        self.assertEqual(status, 200)
        self.assertEqual(messages["messages"][0]["body"], "Привет, обсудим объект?")

        status, _ = self.request(
            f"/api/profile/chats/{chat_id}/messages", token=self.admin_token
        )
        self.assertEqual(status, 403, "An administrator must not gain private-chat access by role alone")

    def test_admin_metrics_and_team_access_fail_closed_on_free_workspaces(self):
                status, overview = self.request(
                    "/api/admin/communication/overview", token=self.admin_token
                )
                self.assertEqual(status, 200)
                self.assertGreaterEqual(overview["users_total"], 3)
                self.assertGreaterEqual(overview["workspaces_total"], 3)
        
                status, object_chats = self.request(
                    "/api/profile/object-chats", token=self.alice_token
                )
                self.assertEqual(status, 200)
                self.assertFalse(object_chats["available"])

    def test_support_escalation_is_visible_to_admin_and_user_cannot_read_admin_queue(self):
        mocked = {"reply": "Подключаю сотрудника поддержки.", "escalate": True,
                  "reason": "user_requested_human"}
        with patch.object(community, "_support_ai_reply", return_value=mocked):
            status, ticket = self.request(
                "/api/support", "POST", {"message": "Позови сотрудника поддержки"},
                self.alice_token,
            )
        self.assertEqual(status, 201)
        self.assertTrue(ticket["needs_human"])
        ticket_id = ticket["ticket_id"]

        status, own_threads = self.request("/api/support/threads", token=self.alice_token)
        self.assertEqual(status, 200)
        self.assertTrue(any(row["id"] == ticket_id for row in own_threads["threads"]))

        status, denied = self.request("/api/admin/communication/threads", token=self.alice_token)
        self.assertEqual(status, 403)

        status, queue = self.request("/api/admin/communication/threads", token=self.admin_token)
        self.assertEqual(status, 200)
        escalated = next(row for row in queue["threads"] if row["id"] == ticket_id)
        self.assertTrue(escalated["needs_human"])
        self.assertEqual(escalated["user_email"], "alice-comms@example.test")

        status, reply = self.request(
            f"/api/admin/communication/threads/{ticket_id}/messages", "POST",
            {"message": "Здравствуйте, я подключился к обращению."},
            self.admin_token,
        )
        self.assertEqual(status, 201)
        self.assertEqual(reply["message"]["sender_type"], "admin")


def identity_for(user_id):
    return community.make_public_id(user_id)


if __name__ == "__main__":
    unittest.main()
