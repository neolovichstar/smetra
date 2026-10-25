"""Access revocation and deletion must cover synchronous and retry paths."""

import json
import os
import unittest
from unittest.mock import patch

from backend import assistant
from tests import test_business


class IsolationBoundaryTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def team(self, label):
        owner, _ = self.account(label + "-owner")
        token, user_id = self.account(label + "-member")
        wid = self.call("/workspace", token=owner)[1]["workspace"]["id"]
        self.assertEqual(self.call("/workspace/members", "POST", {
            "email": label + "-member@test.invalid", "role": "member",
        }, owner, workspace=wid)[0], 200)
        return owner, token, user_id, wid

    def test_synchronous_chat_rechecks_session_before_tools_and_persistence(self):
        token, user_id = self.account("sync-revoked")

        def provider(_messages):
            self.assertEqual(self.call("/auth/logout", "POST", {}, token)[0], 200)
            return {"tool_calls": [{
                "id": "stale-session", "type": "function",
                "function": {"name": "create_clients", "arguments": json.dumps({"name": "Unauthorized proposal"})},
            }]}

        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(
            "backend.assistant.query_model", side_effect=provider
        ), patch("backend.assistant.prepare", wraps=assistant.prepare) as tool:
            status, _ = self.call("/assistant/chat", "POST", {"text": "Create client"}, token)
        self.assertIn(status, (401, 403))
        tool.assert_not_called()
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM assistant_messages WHERE user_id=?", (user_id,)).fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT count(*) FROM assistant_actions WHERE user_id=?", (user_id,)).fetchone()[0], 0)

    def test_write_rechecks_role_after_body_and_before_mutation(self):
        owner, token, _, wid = self.team("write-revoke")
        original = self.mod.Handler.body

        def body(handler):
            data = original(handler)
            if handler.path == "/api/clients" and data.get("name") == "Must not be saved":
                self.assertEqual(self.call("/workspace/members", "POST", {
                    "email": "write-revoke-member@test.invalid", "role": "viewer",
                }, owner, workspace=wid)[0], 200)
            return data

        with patch.object(self.mod.Handler, "body", body):
            status, result = self.call("/clients", "POST", {"name": "Must not be saved"}, token, workspace=wid)
        self.assertEqual(status, 403, result)
        self.assertEqual(self.call("/clients", token=owner, workspace=wid)[1]["items"], [])

    def test_account_deletion_erases_private_auth_and_ai_state_in_shared_workspace(self):
        owner, token, user_id, wid = self.team("erase-private")
        self.assertEqual(self.call("/assistant/conversations", "POST", {"title": "Personal thread"}, token, workspace=wid)[0], 201)
        self.assertEqual(self.call("/clients", "POST", {"name": "Keep shared record"}, token, workspace=wid)[0], 201)
        with self.mod.db() as con:
            moment = self.mod.now()
            con.execute("INSERT INTO assistant_messages(id,workspace_id,user_id,role,content,created_at) VALUES(?,?,?,?,?,?)",
                        ("private-message", wid, user_id, "user", "Private prompt", moment))
            con.execute("INSERT INTO assistant_actions(id,workspace_id,user_id,tool,arguments,summary,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",
                        ("private-action", wid, user_id, "create_clients", "{}", "Private proposal", moment, moment + 600))
            con.execute("INSERT INTO external_identities(provider,subject,user_id,created_at) VALUES(?,?,?,?)",
                        ("yandex", "private-provider-subject", user_id, moment))
            con.execute("INSERT INTO oauth_tickets(ticket_hash,user_id,challenge,expires_at) VALUES(?,?,?,?)",
                        ("ticket", user_id, "challenge", moment + 600))
            con.execute("INSERT INTO oauth_states(state_hash,provider,verifier,browser_hash,link_user_id,expires_at) VALUES(?,?,?,?,?,?)",
                        ("state", "yandex", "private-verifier", "browser", user_id, moment + 600))
        self.assertEqual(self.call("/me", "DELETE", token=token)[0], 200)
        with self.mod.db() as con:
            for table in ("assistant_conversations", "assistant_messages", "assistant_actions", "external_identities", "oauth_tickets"):
                with self.subTest(table=table):
                    self.assertEqual(con.execute(f"SELECT count(*) FROM {table} WHERE user_id=?", (user_id,)).fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT count(*) FROM oauth_states WHERE link_user_id=?", (user_id,)).fetchone()[0], 0)
        self.assertEqual(self.call("/clients", token=owner, workspace=wid)[1]["items"][0]["name"], "Keep shared record")

    def test_blocked_owner_public_change_cannot_be_read_or_approved(self):
        token, user_id = self.account("blocked-change-owner")
        code, obj = self.call("/construction/objects", "POST", {"name": "Private object"}, token)
        self.assertEqual(code, 201, obj)
        endpoint = "/construction/objects/" + obj["object"]["id"] + "/changes"
        code, created = self.call(endpoint, "POST", {
            "title": "Additional scope", "items": [{"name": "Private work", "quantity": "1", "unit_price": 10000}],
        }, token)
        self.assertEqual(code, 201, created)
        code, sent = self.call(endpoint + "/" + created["change"]["id"] + "/send", "POST", {}, token)
        self.assertEqual(code, 200, sent)
        link = sent["change"]["public_token"]
        self.assertEqual(self.call("/public/change?token=" + link)[0], 200)
        with self.mod.db() as con:
            con.execute("UPDATE users SET blocked=1 WHERE id=?", (user_id,))
        self.assertEqual(self.call("/public/change?token=" + link)[0], 404)
        self.assertEqual(self.call("/public/change/respond", "POST", {
            "token": link, "action": "approved", "name": "Client",
        })[0], 404)

    def test_stream_checks_revoked_session_before_first_content_chunk(self):
        token, _ = self.account("stream-revoked")

        def provider(_messages, delta):
            self.assertEqual(self.call("/auth/logout", "POST", {}, token)[0], 200)
            delta("PRIVATE_STREAM_CHUNK")
            return {"content": "PRIVATE_STREAM_CHUNK"}

        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture"), patch(
            "backend.assistant.query_model_stream", side_effect=provider
        ):
            code, content = self.call("/assistant/stream", "POST", {"text": "Check data"}, token, raw=True)
        self.assertEqual(code, 200)
        self.assertNotIn(b"PRIVATE_STREAM_CHUNK", content)
        self.assertNotIn(b"event: delta", content)
        self.assertIn(b"event: error", content)

    def test_admin_mutation_rechecks_role_after_request_body(self):
        admin, admin_id = self.account("revoked-admin")
        _, target_id = self.account("admin-target")
        with self.mod.db() as con:
            con.execute("UPDATE users SET role='admin' WHERE id=?", (admin_id,))
        original = self.mod.Handler.body

        def body(handler):
            data = original(handler)
            if handler.path == "/api/admin/users/" + target_id:
                with self.mod.db() as con:
                    con.execute("UPDATE users SET role='user' WHERE id=?", (admin_id,))
            return data

        with patch.object(self.mod.Handler, "body", body):
            status, result = self.call("/admin/users/" + target_id, "PATCH", {"action": "grant"}, admin)
        self.assertEqual(status, 403, result)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT entitlement_until FROM users WHERE id=?", (target_id,)).fetchone()[0], 0)
