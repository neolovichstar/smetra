"""Regression cases for private snapshots and access revoked during work."""

import json
import os
import unittest
from unittest.mock import patch

from tests import test_business, test_assistant_jobs


class PublicDocumentBoundaryTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account
    quote = test_business.BusinessFlows.quote
    publish = test_business.BusinessFlows.publish

    def test_private_draft_document_is_not_exposed_when_quote_is_later_published(self):
        token, _ = self.account("private-document-source")
        quote = self.quote(token, description="Private internal draft")
        code, result = self.call("/documents", "POST", {"quote_id": quote["id"]}, token)
        self.assertEqual(code, 201, result)
        private_id = result["document"]["id"]
        code, result = self.call("/quotes/" + quote["id"], "PATCH", {
            "revision": quote["revision"], "description": "Public agreed scope",
        }, token)
        self.assertEqual(code, 200, result)
        quote = self.publish(token, result["quote"])
        link = quote["public_url"].split("quote=")[1]
        code, public = self.call("/public/quote?token=" + link)
        self.assertEqual(code, 200, public)
        self.assertNotIn(private_id, [doc["id"] for doc in public["documents"]])
        self.assertEqual(self.call("/public/document?token=" + link + "&id=" + private_id)[0], 404)
        self.assertEqual(self.call("/documents/" + private_id + "/pdf", token=token, raw=True)[0], 200)
        code, shared = self.call("/documents", "POST", {"quote_id": quote["id"]}, token)
        self.assertEqual(code, 201, shared)
        shared_id = shared["document"]["id"]
        self.assertEqual(self.call("/public/document?token=" + link + "&id=" + shared_id, raw=True)[0], 200)
        public = self.call("/public/quote?token=" + link)[1]
        self.assertEqual([doc["id"] for doc in public["documents"]], [shared_id])


class WorkerRevocationTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def setUp(self):
        test_business.BusinessFlows.setUp(self)
        settings = patch.dict(os.environ, ASSISTANT_WORKER_SECRET=test_assistant_jobs.SECRET,
                              OPENROUTER_API_KEY="test-only")
        settings.start()
        self.addCleanup(settings.stop)

    def test_session_or_write_role_revoked_during_model_call_stops_tools_and_commit(self):
        for revoke in ("session", "viewer"):
            with self.subTest(revoke=revoke):
                owner, _ = self.account("team-owner-" + revoke)
                token, user_id = self.account("inflight-" + revoke)
                wid = self.call("/workspace", token=owner)[1]["workspace"]["id"]
                code, result = self.call("/workspace/members", "POST", {
                    "email": "inflight-" + revoke + "@test.invalid", "role": "member",
                }, owner, workspace=wid)
                self.assertEqual(code, 200, result)
                code, queued = self.call("/assistant/jobs", "POST", {
                    "text": "Create a client",
                }, token, workspace=wid, key="revoke-" + revoke)
                self.assertEqual(code, 202, queued)
                job_id = queued["job"]["id"]

                def provider(_messages):
                    if revoke == "session":
                        code, result = self.call("/auth/logout", "POST", {}, token)
                    else:
                        code, result = self.call("/workspace/members", "POST", {
                            "email": "inflight-" + revoke + "@test.invalid", "role": "viewer",
                        }, owner, workspace=wid)
                    self.assertEqual(code, 200, result)
                    return {"tool_calls": [{
                        "id": "revoked-tool", "type": "function",
                        "function": {"name": "create_clients", "arguments": json.dumps({"name": "Must not survive"})},
                    }]}

                with patch("backend.assistant.query_model", side_effect=provider), patch(
                    "backend.assistant.prepare", wraps=__import__("backend.assistant", fromlist=["prepare"]).prepare
                ) as tool:
                    code, result = self.call("/cron/assistant", token=test_assistant_jobs.worker_token())
                self.assertEqual(code, 200, result)
                tool.assert_not_called()
                with self.mod.db() as con:
                    job = con.execute("SELECT * FROM assistant_jobs WHERE id=?", (job_id,)).fetchone()
                    self.assertEqual(job["status"], "failed")
                    self.assertEqual(job["quota_refunded"], 1)
                    self.assertEqual(con.execute("SELECT count(*) FROM assistant_messages WHERE user_id=?", (user_id,)).fetchone()[0], 0)
                    self.assertEqual(con.execute("SELECT count(*) FROM assistant_actions WHERE user_id=?", (user_id,)).fetchone()[0], 0)

    def test_revocation_on_final_plain_answer_prevents_committing_history(self):
        token, user_id = self.account("inflight-final-answer")
        code, queued = self.call("/assistant/jobs", "POST", {"text": "Check records"}, token, key="final-answer")
        self.assertEqual(code, 202, queued)

        def provider(_messages):
            with self.mod.db() as con:
                con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            return {"content": "This must not commit"}

        with patch("backend.assistant.query_model", side_effect=provider):
            code, result = self.call("/cron/assistant", token=test_assistant_jobs.worker_token())
        self.assertEqual(code, 200, result)
        with self.mod.db() as con:
            job = con.execute("SELECT * FROM assistant_jobs WHERE id=?", (queued["job"]["id"],)).fetchone()
            self.assertEqual(job["status"], "failed")
            self.assertEqual(con.execute("SELECT count(*) FROM assistant_messages WHERE user_id=?", (user_id,)).fetchone()[0], 0)
