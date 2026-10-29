"""Real PostgreSQL checks for live authority inside AI confirmation transactions."""
import os
import json
import time
import uuid
import unittest
from unittest.mock import patch

from backend import assistant
from backend.business import DomainError, Service
from tests import test_assistant_delivery_postgres as fixture


tearDownModule = fixture.tearDownModule


@unittest.skipUnless(os.getenv("SMETRA_TEST_ADMIN_URL") and os.getenv("SMETRA_TEST_RUNTIME_URL"),
                     "requires disposable PostgreSQL and limited runtime role")
class AssistantActionPostgresTests(unittest.TestCase):
    setUp = fixture.DurableChatPostgresTests.setUp
    clean = fixture.DurableChatPostgresTests.clean

    def prepared(self):
        service = Service(None, self.admin, "https://example.test")
        service.user = self.admin.execute("SELECT * FROM users WHERE id=?", (self.uid,)).fetchone()
        service.wid, service.role = self.wid, "owner"
        return assistant.prepare(service, "create_clients", {"name": "Confirmed client"})

    def runtime_service(self):
        service, handler = fixture.DurableChatPostgresTests.service(self)
        handler.session_token_hash = self.session
        self.addCleanup(service.con.close)
        return service

    def test_runtime_confirmation_commits_once_and_replays_saved_result(self):
        action = self.prepared()
        for _ in range(2):
            service = self.runtime_service()
            with patch("backend.redis_infra.acquire_lock", return_value=fixture.Lease(None, "", "")):
                result = assistant.confirm(service, action["id"])
            self.assertTrue(result["ok"])
            service.runtime_connection.finish(True)
        self.assertEqual(self.admin.execute(
            "SELECT count(*) FROM clients WHERE workspace_id=?", (self.wid,),
        ).fetchone()[0], 1)

    def test_runtime_cannot_apply_using_role_cached_before_demotion(self):
        action = self.prepared()
        service = self.runtime_service()
        self.admin.execute("UPDATE workspace_members SET role='viewer' WHERE workspace_id=? AND user_id=?",
                           (self.wid, self.uid))
        with self.assertRaises(DomainError) as caught:
            assistant._confirm(service, action["id"])
        self.assertEqual(caught.exception.status, 403)
        service.runtime_connection.finish(False)
        self.assertEqual(self.admin.execute("SELECT status FROM assistant_actions WHERE id=?",
                                            (action["id"],)).fetchone()[0], "pending")

    def test_runtime_cannot_apply_after_session_revocation(self):
        action = self.prepared()
        service = self.runtime_service()
        self.admin.execute("DELETE FROM sessions WHERE user_id=?", (self.uid,))
        with self.assertRaises(DomainError) as caught:
            assistant._confirm(service, action["id"])
        self.assertIn(caught.exception.status, (401, 403))
        service.runtime_connection.finish(False)
        self.assertEqual(self.admin.execute("SELECT count(*) FROM clients WHERE workspace_id=?",
                                            (self.wid,)).fetchone()[0], 0)


@unittest.skipUnless(os.getenv("SMETRA_TEST_ADMIN_URL") and os.getenv("SMETRA_TEST_RUNTIME_URL"),
                     "requires disposable PostgreSQL")
class QuoteChatPostgresTests(unittest.TestCase):
    setUp = fixture.DurableChatPostgresTests.setUp
    clean = fixture.DurableChatPostgresTests.clean

    def published_quote(self):
        quote_id, recipient_id = str(uuid.uuid4()), str(uuid.uuid4())
        moment = int(time.time())
        self.admin.execute(
            "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,'unused','Recipient',?,?)",
            (recipient_id, recipient_id + "@test.invalid", moment, moment),
        )
        self.addCleanup(self.admin.execute, "DELETE FROM users WHERE id=?", (recipient_id,))
        self.admin.execute(
            "INSERT INTO quotes(id,user_id,title,client,description,amount_kopecks,status,public_token,"
            "created_at,updated_at,workspace_id,published_version,approval_state) "
            "VALUES(?,?,'Reviewed quote','Client','',10000,'sent',?,?,?, ?,1,'sent')",
            (quote_id, self.uid, uuid.uuid4().hex, moment, moment, self.wid),
        )
        self.admin.execute(
            "INSERT INTO quote_versions VALUES(?,1,?,?,'Reviewed',?)",
            (quote_id, json.dumps({"title": "Reviewed quote", "client": "Client", "description": "",
                                  "currency": "RUB", "amount_kopecks": 10000, "items": [], "version": 1}),
             self.uid, moment),
        )
        self.addCleanup(self.admin.execute, "DELETE FROM quotes WHERE id=?", (quote_id,))
        self.addCleanup(self.admin.execute, "DELETE FROM chat_conversations WHERE quote_id=?", (quote_id,))
        return quote_id, recipient_id

    def test_same_publication_is_delivered_once_without_widening_runtime_grants(self):
        from backend.community import send_quote_to_user
        quote_id, recipient = self.published_quote()
        first = send_quote_to_user(self.admin, self.wid, quote_id, self.uid, recipient, version=1)
        second = send_quote_to_user(self.admin, self.wid, quote_id, self.uid, recipient, version=1)
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(self.admin.execute(
            "SELECT count(*) FROM chat_messages WHERE conversation_id=?", (first["conversation_id"],),
        ).fetchone()[0], 1)

    def test_removed_author_cannot_deliver_using_cached_workspace_id(self):
        from backend.community import send_quote_to_user
        quote_id, recipient = self.published_quote()
        self.admin.execute("DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?", (self.wid, self.uid))
        with self.assertRaises(DomainError) as caught:
            send_quote_to_user(self.admin, self.wid, quote_id, self.uid, recipient, version=1)
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(self.admin.execute(
            "SELECT count(*) FROM chat_conversations WHERE quote_id=?", (quote_id,),
        ).fetchone()[0], 0)
