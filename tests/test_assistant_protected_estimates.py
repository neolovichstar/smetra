"""Protected-link tools never mutate or send before an authorized confirmation."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.assistant import prepare, tools
from backend.business import Service
from backend.protected_estimates import digest
from tests import test_protected_estimates as fixtures


class ProtectedEstimateToolTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.ProtectedEstimateTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.ProtectedEstimateTests.tearDownClass.__func__)
    setUp = fixtures.ProtectedEstimateTests.setUp
    call = fixtures.ProtectedEstimateTests.call
    account = fixtures.ProtectedEstimateTests.account
    link = fixtures.ProtectedEstimateTests.link

    def proposal(self, name, args):
        with self.mod.db() as con:
            service = Service(SimpleNamespace(headers={}), con, self.mod.ORIGIN)
            service.user = con.execute("SELECT * FROM users WHERE id=?", (self.owner_id,)).fetchone()
            service.wid = con.execute("SELECT id FROM workspaces WHERE owner_id=?", (self.owner_id,)).fetchone()[0]
            service.role = "owner"
            return prepare(service, name, args)

    def test_tool_catalog_includes_reads_and_confirmed_writes(self):
        names = {tool["function"]["name"] for tool in tools()}
        self.assertTrue({"list_protected_estimates", "get_protected_estimate_access", "create_protected_estimate",
                         "update_protected_estimate", "revoke_protected_estimate", "send_protected_estimate"} <= names)

    def test_create_is_a_proposal_and_confirmation_persists_no_raw_secrets(self):
        proposal = self.proposal("create_protected_estimate", {
            "quote_id": self.quote["id"], "recipient_email": self.recipient_email, "code_mode": "generate",
        })
        self.assertIn("preview", proposal)
        preview = {row["field"]: row["after"] for row in proposal["preview"]["rows"]}
        self.assertEqual(preview["Почта получателя"], self.recipient_email)
        self.assertEqual(preview["Скачивание PDF"], "Выключено")
        self.assertEqual(preview["Закупочные цены и внутренняя наценка"], "Скрыты всегда")
        self.assertTrue(all(not isinstance(row["after"], dict) for row in proposal["preview"]["rows"]))
        self.assertEqual(self.call("/protected-links?quote_id=" + self.quote["id"], token=self.owner)[1]["links"], [])
        status, result = self.call("/assistant/confirm", "POST", {"id": proposal["id"]}, self.owner)
        self.assertEqual(status, 200, result)
        token = result["result"]["url"].split("#")[1]
        code = result["result"]["access_code"]
        with self.mod.db() as con:
            stored = con.execute("SELECT arguments,result FROM assistant_actions WHERE id=?", (proposal["id"],)).fetchone()
            self.assertNotIn(token, str(dict(stored)))
            self.assertNotIn(code, str(dict(stored)))
            self.assertEqual(con.execute("SELECT token_hash FROM protected_quote_links WHERE id=?", (result["result"]["link"]["id"],)).fetchone()[0], digest(token))
        status, replay = self.call("/assistant/confirm", "POST", {"id": proposal["id"]}, self.owner)
        self.assertEqual(status, 200, replay)
        self.assertNotIn("url", replay["result"])
        self.assertNotIn("access_code", replay["result"])

    def test_model_can_prepare_but_not_execute_link_creation(self):
        calls = [
            {"content": None, "tool_calls": [{"id": "protected-call", "type": "function", "function": {
                "name": "create_protected_estimate", "arguments": json.dumps({"quote_id": self.quote["id"]}),
            }}]},
            {"content": "Подготовил защищённую ссылку к подтверждению.", "tool_calls": []},
        ]
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch("backend.assistant.query_model", side_effect=calls):
            status, result = self.call("/assistant/chat", "POST", {"text": "Подготовь защищённую ссылку"}, self.owner)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["actions"][0]["tool"], "create_protected_estimate")
        self.assertEqual(self.call("/protected-links?quote_id=" + self.quote["id"], token=self.owner)[1]["links"], [])

    def test_smtp_send_requires_confirmation_and_honors_failure_and_retry(self):
        link, _ = self.link()
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=? WHERE id=?", (self.mod.now(), self.owner_id))
        proposal = self.proposal("send_protected_estimate", {"id": link["id"]})
        self.assertIn(self.recipient_email, proposal["summary"])
        self.assertIn("прежний адрес", proposal["preview"]["rows"][0]["after"])
        with patch("backend.app.mail") as mail:
            status, _ = self.call("/protected-links/" + link["id"] + "/send", "POST", {"revision": 1}, self.owner)
        self.assertEqual(status, 400)
        mail.assert_not_called()
        with patch("backend.app.mail", side_effect=self.mod.ApiError(503, "fixture SMTP down")):
            failed = self.call("/assistant/confirm", "POST", {"id": proposal["id"]}, self.owner)
        self.assertEqual(failed[0], 503, failed)
        self.assertEqual(self.call("/protected-links/" + link["id"], token=self.owner)[1]["link"]["revision"], 1)
        with patch("backend.app.mail") as mail:
            sent = self.call("/assistant/confirm", "POST", {"id": proposal["id"]}, self.owner)
            self.assertEqual(sent[0], 200, sent)
            self.assertEqual(mail.call_args.args[0], self.recipient_email)
            self.assertIn("/protected-estimate#", mail.call_args.args[2])
            replay = self.call("/assistant/confirm", "POST", {"id": proposal["id"]}, self.owner)
        self.assertEqual(replay[0], 200, replay)
        mail.assert_called_once()

    def test_stale_settings_and_downgraded_role_cannot_confirm_or_replay(self):
        link, _ = self.link()
        proposal = self.proposal("update_protected_estimate", {"id": link["id"], "settings": {"allow_pdf": True}})
        self.assertEqual(self.call("/protected-links/" + link["id"], "PATCH", {"revision": 1, "settings": {"watermark": False}}, self.owner)[0], 200)
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": proposal["id"]}, self.owner)[0], 409)
        fresh = self.proposal("revoke_protected_estimate", {"id": link["id"]})
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": fresh["id"]}, self.owner)[0], 200)
        # The user remains a member but loses managerial rights; a cached
        # successful action result must not bypass the current permission gate.
        with self.mod.db() as con:
            con.execute("UPDATE workspace_members SET role='member' WHERE workspace_id=(SELECT id FROM workspaces WHERE owner_id=?) AND user_id=?", (self.owner_id, self.owner_id))
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": fresh["id"]}, self.owner)[0], 403)
