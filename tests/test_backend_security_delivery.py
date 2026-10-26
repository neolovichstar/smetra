"""HTTP regressions for webhook forgery, revoked access and reliable chat delivery."""
import concurrent.futures
import hashlib
import http.client
import json
import os
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend import app, cloud_drives, community
from backend.redis_infra import RedisUnavailable
from tests import test_communication_api as fixtures


class SecurityDeliveryApiTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.CommunicationApiTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.CommunicationApiTests.tearDownClass.__func__)
    register = classmethod(fixtures.CommunicationApiTests.register.__func__)
    request = fixtures.CommunicationApiTests.request

    def setUp(self):
        app.RATE.clear()
        env = patch.dict(os.environ, {
            "YOOKASSA_MODE": "live", "YOOKASSA_SHOP_ID": "security-fixture",
            "YOOKASSA_SECRET_KEY": "fixture-only", "YOOKASSA_MERCHANT_TYPE": "self_employed",
        })
        env.start()
        self.addCleanup(env.stop)

    def payment(self, status="pending"):
        ident = app.uid()
        with app.db() as con:
            con.execute(
                "INSERT INTO payments(id,user_id,provider_id,plan,amount_kopecks,status,"
                "idempotency_key,confirmation_url,created_at,activated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (ident, self.alice_id, "provider-" + ident, "pro_month", 49000, status,
                 "checkout-" + ident, "https://example.test/pay", app.now(),
                 app.now() if status == "succeeded" else None),
            )
            return dict(con.execute("SELECT * FROM payments WHERE id=?", (ident,)).fetchone())

    def remote(self, payment, **changes):
        return {
            "id": payment["provider_id"], "status": "succeeded", "paid": True, "test": False,
            "recipient": {"account_id": "security-fixture"},
            "metadata": {"user_id": self.alice_id, "plan": payment["plan"]},
            "amount": {"value": "490.00", "currency": "RUB"},
        } | changes

    def callback(self, payment, event="payment.succeeded", **extra):
        return self.request("/api/webhooks/yookassa", "POST", {
            "type": "notification", "event": event,
            "object": {"id": payment["provider_id"]},
        } | extra)

    def chat(self, kind="direct", workspace_id=""):
        with app.db() as con:
            cid = community._new_conversation(
                con, kind, "Private project", self.alice_id, workspace_id=workspace_id,
            )
            community._add_member(con, cid, self.alice_id)
            community._add_member(con, cid, self.bob_id)
        return cid

    def test_fake_success_never_credits_a_provider_pending_payment(self):
        payment = self.payment()
        with patch.object(app.Handler, "provider_payment", return_value=self.remote(
            payment, status="pending", paid=False,
        )):
            status, _ = self.callback(payment)
        self.assertEqual(status, 200)
        with app.db() as con:
            self.assertEqual(con.execute("SELECT status FROM payments WHERE id=?", (payment["id"],)).fetchone()[0], "pending")

    def test_callback_checks_shop_environment_amount_metadata_and_paid(self):
        variants = (
            {"recipient": {"account_id": "different-shop"}},
            {"test": True}, {"amount": {"value": "0.01", "currency": "RUB"}},
            {"metadata": {"user_id": self.bob_id, "plan": "pro_month"}},
            {"paid": False}, {"amount": None}, {"metadata": []},
        )
        for changes in variants:
            with self.subTest(changes=changes):
                payment = self.payment()
                with patch.object(app.Handler, "provider_payment", return_value=self.remote(payment, **changes)):
                    status, _ = self.callback(payment)
                self.assertEqual(status, 409)
                with app.db() as con:
                    self.assertEqual(con.execute("SELECT status FROM payments WHERE id=?", (payment["id"],)).fetchone()[0], "pending")

    def test_callback_replay_does_not_extend_subscription_twice(self):
        payment = self.payment()
        with patch.object(app.Handler, "provider_payment", return_value=self.remote(payment)) as provider:
            self.assertEqual(self.callback(payment)[0], 200)
            with app.db() as con:
                before = con.execute("SELECT entitlement_until FROM users WHERE id=?", (self.alice_id,)).fetchone()[0]
            self.assertEqual(self.callback(payment)[0], 200)
        self.assertEqual(provider.call_count, 1)
        with app.db() as con:
            self.assertEqual(con.execute("SELECT entitlement_until FROM users WHERE id=?", (self.alice_id,)).fetchone()[0], before)

    def test_pending_callback_flood_has_a_shared_object_limit(self):
        payment = self.payment()
        with patch.object(app.Handler, "provider_payment", return_value=self.remote(payment, status="pending", paid=False)) as provider:
            statuses = [self.callback(payment)[0] for _ in range(7)]
        self.assertEqual(statuses, [200] * 6 + [429])
        self.assertEqual(provider.call_count, 6)

    def test_refund_must_match_requested_refund_and_original_payment(self):
        payment = self.payment(status="succeeded")
        rid = "refund-" + app.uid()
        for changes in ({"id": "other"}, {"payment_id": "other"}):
            with self.subTest(changes=changes), patch.object(app.Handler, "provider_call", return_value={
                "id": rid, "payment_id": payment["provider_id"], "status": "succeeded",
                "amount": {"value": "490.00", "currency": "RUB"},
            } | changes), patch.object(app.Handler, "apply_refund", side_effect=AssertionError("applied forged refund")):
                status, _ = self.request("/api/webhooks/yookassa", "POST", {
                    "event": "refund.succeeded", "object": {"id": rid, "payment_id": payment["provider_id"]},
                })
                self.assertEqual(status, 409)

    def test_full_refund_rechecks_payment_and_duplicate_is_local(self):
        payment = self.payment(status="succeeded")
        rid = "refund-" + app.uid()
        refund = {"id": rid, "payment_id": payment["provider_id"], "status": "succeeded",
                  "amount": {"value": "490.00", "currency": "RUB"}}
        with patch.object(app.Handler, "provider_call", return_value=refund) as fetch_refund, \
                patch.object(app.Handler, "provider_payment", return_value=self.remote(payment)) as fetch_payment:
            data = {"event": "refund.succeeded", "object": {"id": rid, "payment_id": payment["provider_id"]}}
            self.assertEqual(self.request("/api/webhooks/yookassa", "POST", data)[0], 200)
            self.assertEqual(self.request("/api/webhooks/yookassa", "POST", data)[0], 200)
        self.assertEqual(fetch_refund.call_count, 1)
        self.assertEqual(fetch_payment.call_count, 1)
        with app.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM refunds WHERE provider_id=?", (rid,)).fetchone()[0], 1)

    def test_invalid_webhook_method_is_rejected_before_database(self):
        with patch.object(app, "db", side_effect=AssertionError("allocated a DB connection")):
            status, _ = self.request("/api/webhooks/yookassa")
        self.assertEqual(status, 405)

    def test_revoked_object_chat_member_cannot_list_read_or_write(self):
        with app.db() as con:
            wid = con.execute("SELECT id FROM workspaces WHERE owner_id=?", (self.alice_id,)).fetchone()[0]
            con.execute("UPDATE workspaces SET plan='team',subscription_status='active',entitlement_until=? WHERE id=?", (app.now() + 3600, wid))
            con.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'member') ON CONFLICT DO NOTHING", (wid, self.bob_id))
        cid = self.chat("object", wid)
        url = "/api/profile/chats/" + cid + "/messages"
        self.assertEqual(self.request(url, token=self.bob_token)[0], 200)
        with app.db() as con:
            con.execute("DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?", (wid, self.bob_id))
        self.assertEqual(self.request(url, token=self.bob_token)[0], 403)
        self.assertEqual(self.request(url, "POST", {"message": "no access"}, self.bob_token)[0], 403)
        for path in ("/api/profile/chats", "/api/profile/object-chats"):
            status, payload = self.request(path, token=self.bob_token)
            self.assertEqual(status, 200)
            self.assertNotIn(cid, [c["id"] for c in payload["chats"]])

    def test_private_chat_list_omits_the_other_persons_email(self):
        cid = self.chat()
        status, payload = self.request("/api/profile/chats", token=self.bob_token)
        self.assertEqual(status, 200)
        row = next(c for c in payload["chats"] if c["id"] == cid)
        self.assertEqual(row["user_email"], "")
        self.assertNotIn("alice-comms@example.test", json.dumps(payload))

    def test_initial_history_contains_recent_messages_after_first_hundred(self):
        cid = self.chat()
        moment = app.now() - 200
        with app.db() as con:
            con.executemany(
                "INSERT INTO chat_messages(id,conversation_id,sender_id,sender_type,body,metadata,created_at) VALUES(?,?,?,'user',?,'{}',?)",
                [(f"history-{cid}-{i:03}", cid, self.alice_id, str(i), moment + i) for i in range(125)],
            )
        status, payload = self.request("/api/profile/chats/" + cid + "/messages", token=self.bob_token)
        self.assertEqual(status, 200)
        self.assertEqual([int(m["body"]) for m in payload["messages"]], list(range(25, 125)))
        with app.db() as con:
            self.assertEqual([int(m["body"]) for m in community._messages(con, cid, after=moment + 10, limit=20)], list(range(11, 31)))
            self.assertEqual([int(m["body"]) for m in community._messages(con, cid, limit=20)], list(range(105, 125)))

    def test_chat_insert_and_conversation_update_rollback_together(self):
        cid = self.chat()
        original = community._add_message
        def fail_after_insert(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("fixture failure after insert")
        with patch.object(community, "_add_message", side_effect=fail_after_insert):
            status, _ = self.request("/api/profile/chats/" + cid + "/messages", "POST", {"message": "rollback"}, self.alice_token)
        self.assertEqual(status, 500)
        with app.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM chat_messages WHERE conversation_id=?", (cid,)).fetchone()[0], 0)

    def test_successful_communication_request_sends_exactly_one_http_response(self):
        cid = self.chat()
        responses = []
        original = app.Handler.send_response
        def record(handler, code, message=None):
            responses.append(code)
            return original(handler, code, message)
        with patch.object(app.Handler, "send_response", record):
            self.assertEqual(self.request("/api/profile/chats/" + cid + "/messages", token=self.bob_token)[0], 200)
        self.assertEqual(responses, [200])

    def test_support_creation_endpoints_share_limit_before_model_or_writes(self):
        token, user_id = self.register("Support", app.uid() + "@example.test", "user")
        with patch.object(community, "_support_ai_reply", return_value={"reply": "Ready", "escalate": False, "reason": ""}) as model:
            for i in range(5):
                path = "/api/support" if i % 2 else "/api/support/threads"
                self.assertEqual(self.request(path, "POST", {"subject": "Help", "message": "A billing question"}, token)[0], 201)
            self.assertEqual(self.request("/api/support", "POST", {"message": "Extra ticket"}, token)[0], 429)
        self.assertEqual(model.call_count, 2)
        with app.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM chat_conversations WHERE created_by=?", (user_id,)).fetchone()[0], 5)

    def test_redis_failure_rejects_support_ai_before_creating_ticket(self):
        token, user_id = self.register("Redis", app.uid() + "@example.test", "user")
        with patch("backend.redis_infra.rate_limit", side_effect=RedisUnavailable("fixture outage")), \
                patch.object(community, "_support_ai_reply", side_effect=AssertionError("unlimited model call")):
            self.assertEqual(self.request("/api/support", "POST", {"message": "How to create an estimate?"}, token)[0], 503)
        with app.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM chat_conversations WHERE created_by=?", (user_id,)).fetchone()[0], 0)

    def test_reset_invalidates_all_other_links_and_sessions(self):
        token, user_id = self.register("Reset", app.uid() + "@example.test", "user")
        with app.db() as con:
            first = app.create_email_token(con, user_id, "reset", 1800)
            second = app.create_email_token(con, user_id, "reset", 1800)
        self.assertEqual(self.request("/api/auth/reset/confirm", "POST", {"token": first, "password": "new secure password one"})[0], 200)
        self.assertIn(self.request("/api/auth/reset/confirm", "POST", {"token": second, "password": "new secure password two"})[0], (400, 409))
        self.assertEqual(self.request("/api/me", token=token)[0], 401)
        with app.db() as con:
            row = con.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
            self.assertTrue(app.verify_password("new secure password one", row[0]))
            self.assertEqual(con.execute("SELECT count(*) FROM email_tokens WHERE user_id=? AND purpose='reset' AND consumed_at IS NULL", (user_id,)).fetchone()[0], 0)

    def test_two_concurrent_reset_links_have_only_one_winner(self):
        _, user_id = self.register("Concurrent reset", app.uid() + "@example.test", "user")
        with app.db() as con:
            tokens = [app.create_email_token(con, user_id, "reset", 1800) for _ in range(2)]
        def reset(token):
            return self.request("/api/auth/reset/confirm", "POST", {"token": token, "password": "concurrent secure password"})[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(reset, tokens))
        self.assertEqual(statuses.count(200), 1)
        self.assertTrue(all(s in (200, 400, 409) for s in statuses), statuses)

    def test_deep_json_has_controlled_400_response(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        body = '{"value":' + "[" * 1100 + "0" + "]" * 1100 + "}"
        connection.request("POST", "/api/auth/register", body, {"Content-Type": "application/json"})
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        self.assertNotIn("Traceback", response.read().decode())
        connection.close()

    def test_parallel_messages_are_committed_before_ack_and_visible_to_peer(self):
        cid = self.chat()
        url = "/api/profile/chats/" + cid + "/messages"
        def send(index):
            return self.request(url, "POST", {"message": f"parallel-{index}"}, self.alice_token)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            sent = list(executor.map(send, range(12)))
        self.assertTrue(all(status == 201 for status, _ in sent), sent)
        status, payload = self.request(url, token=self.bob_token)
        self.assertEqual(status, 200)
        self.assertEqual({m["id"] for m in payload["messages"]}, {data["message"]["id"] for _, data in sent})
        self.assertEqual({m["body"] for m in payload["messages"]}, {f"parallel-{i}" for i in range(12)})


class CloudWebhookSecurityTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.addCleanup(self.con.close)
        self.con.executescript("""
            CREATE TABLE cloud_watch_channels(channel_id TEXT, token_hash TEXT, resource_id TEXT, connection_id TEXT, status TEXT, expires_at INTEGER);
            CREATE TABLE cloud_connections(id TEXT, status TEXT);
            CREATE TABLE cloud_folder_bindings(connection_id TEXT, status TEXT, sync_requested INTEGER, next_sync_at INTEGER, updated_at INTEGER);
        """)
        self.con.execute("INSERT INTO cloud_connections VALUES('connection','active')")
        self.con.execute("INSERT INTO cloud_watch_channels VALUES(?,?,?,'connection','active',?)", ("channel", hashlib.sha256(b"secret").hexdigest(), "resource", app.now() + 3600))
        self.con.execute("INSERT INTO cloud_folder_bindings VALUES('connection','active',0,0,0)")
        self.handler = SimpleNamespace(headers={
            "X-Goog-Channel-ID": "channel", "X-Goog-Channel-Token": "secret", "X-Goog-Resource-ID": "resource",
        }, throttle=lambda *a: None, client_address=("127.0.0.1", 0))

    def test_wrong_token_resource_expiry_and_disabled_connection_cannot_schedule(self):
        for header, value in (("X-Goog-Channel-Token", "forged"), ("X-Goog-Resource-ID", "forged")):
            with self.subTest(header=header), patch.dict(self.handler.headers, {header: value}):
                with self.assertRaises(community.ApiError) as error:
                    cloud_drives.webhook(self.handler, self.con)
                self.assertEqual(error.exception.status, 401)
        self.con.execute("UPDATE cloud_connections SET status='disabled'")
        with self.assertRaises(community.ApiError) as error:
            cloud_drives.webhook(self.handler, self.con)
        self.assertEqual(error.exception.status, 401)
        self.con.execute("UPDATE cloud_connections SET status='active'")
        self.con.execute("UPDATE cloud_watch_channels SET expires_at=0")
        with self.assertRaises(community.ApiError):
            cloud_drives.webhook(self.handler, self.con)
        self.assertEqual(self.con.execute("SELECT sync_requested FROM cloud_folder_bindings").fetchone()[0], 0)

    def test_repeated_valid_notification_only_schedules_once(self):
        self.assertTrue(cloud_drives.webhook(self.handler, self.con)["accepted"])
        changed = self.con.total_changes
        self.assertTrue(cloud_drives.webhook(self.handler, self.con)["accepted"])
        self.assertEqual(self.con.total_changes, changed)
        self.assertEqual(self.con.execute("SELECT sync_requested FROM cloud_folder_bindings").fetchone()[0], 1)


@unittest.skipUnless(os.getenv("SMETRA_TEST_ADMIN_URL"), "requires disposable PostgreSQL")
class PostgresChatPrivacyTests(unittest.TestCase):
    def test_postgres_chat_queries_enforce_revocation_and_latest_history(self):
        from backend import postgres
        env = patch.dict(os.environ, {
            "DATABASE_URL": os.environ["SMETRA_TEST_ADMIN_URL"], "SMETRA_LOCAL_POSTGRES": "1",
        })
        with env:
            con = postgres.Connection()
            self.addCleanup(con.close)
            first, second, wid = (app.uid() for _ in range(3))
            cid = None
            try:
                for ident in (first, second):
                    con.execute(
                        "INSERT INTO users(id,email,password_hash,name,created_at) VALUES(?,?,'fixture','QA',0)",
                        (ident, ident + "@example.test"),
                    )
                con.execute("INSERT INTO workspaces(id,owner_id,name,created_at) VALUES(?,?,'QA',0)", (wid, first))
                con.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'member')", (wid, second))
                cid = community._new_conversation(con, "object", "Private", first, workspace_id=wid)
                community._add_member(con, cid, first)
                community._add_member(con, cid, second)
                self.assertTrue(community._member(con, cid, second))
                with app.business.transaction(con, lock_scopes=(f"workspace:{wid}",)):
                    for i in range(125):
                        community._add_message(con, cid, first, "user", str(i))
                        con.execute(
                            "UPDATE chat_messages SET created_at=? WHERE conversation_id=? AND body=?",
                            (100 + i, cid, str(i)),
                        )
                rows = community._messages(con, cid)
                self.assertEqual([int(r["body"]) for r in rows], list(range(25, 125)))
                self.assertEqual(community._list_conversations(con, second, ("object",))[0]["user_email"], "")
                con.execute("DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?", (wid, second))
                self.assertIsNone(community._member(con, cid, second))
                self.assertEqual(community._list_conversations(con, second, ("object",)), [])
                self.assertTrue(community._member(con, cid, first), "workspace owner remains authorized")
            finally:
                if cid:
                    con.execute("DELETE FROM chat_conversations WHERE id=?", (cid,))
                con.execute("DELETE FROM workspaces WHERE id=?", (wid,))
                for ident in (first, second):
                    con.execute("DELETE FROM users WHERE id=?", (ident,))
