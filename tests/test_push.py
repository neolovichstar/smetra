import hashlib
import hmac
import os
import sqlite3
import unittest
from unittest.mock import patch

from backend import app, push
from backend.postgres import translate


class Handler:
    def __init__(self):
        self.headers = {}
        self.session_token_hash = "session-hash"

    def throttle(self, *args):
        pass


class Service:
    def __init__(self, con):
        self.con = con
        self.user = {"id": "u1"}
        self.wid = "w1"
        self.h = Handler()


class PushTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
            CREATE TABLE users(id TEXT PRIMARY KEY);
            CREATE TABLE workspaces(id TEXT PRIMARY KEY);
            CREATE TABLE workspace_members(workspace_id TEXT,user_id TEXT,role TEXT);
            CREATE TABLE notifications(id TEXT PRIMARY KEY, workspace_id TEXT, message TEXT, entity_id TEXT, created_at INTEGER);
            CREATE TABLE sessions(id TEXT PRIMARY KEY,user_id TEXT,token_hash TEXT,expires_at INTEGER);
            CREATE TABLE push_devices(id TEXT PRIMARY KEY,installation_id TEXT UNIQUE,user_id TEXT,session_token_hash TEXT,token TEXT UNIQUE,platform TEXT,created_at INTEGER,updated_at INTEGER,last_seen INTEGER);
            CREATE TABLE push_outbox(id TEXT PRIMARY KEY,workspace_id TEXT,notification_id TEXT,title TEXT,body TEXT,entity_id TEXT,created_at INTEGER,next_attempt_at INTEGER,attempts INTEGER DEFAULT 0,lease_until INTEGER DEFAULT 0,sent_at INTEGER,last_error TEXT DEFAULT '');
            CREATE TABLE push_deliveries(id TEXT PRIMARY KEY,workspace_id TEXT,outbox_id TEXT,device_id TEXT,attempts INTEGER DEFAULT 0,next_attempt_at INTEGER,lease_until INTEGER DEFAULT 0,sent_at INTEGER,completed_at INTEGER,last_error TEXT DEFAULT '',created_at INTEGER,UNIQUE(outbox_id,device_id));
        """)
        self.con.execute("INSERT INTO users VALUES('u1')")
        self.con.execute("INSERT INTO workspaces VALUES('w1')")
        self.con.execute("INSERT INTO workspace_members VALUES('w1','u1','owner')")
        self.con.execute("INSERT INTO sessions VALUES('s1','u1','session-hash',9999999999)")
        self.con.execute("INSERT INTO notifications VALUES('n1','w1','Изменение','q1',1)")
        self.service = Service(self.con)
        self.installation = "a2a2a2a2-1234-4234-8234-123456789abc"
        self.token = "token-value-for-unit-tests-123456"

    def tearDown(self):
        self.con.close()

    def test_registration_is_idempotent_and_token_is_not_returned(self):
        _, result = push.handle(self.service, "POST", [], {"installation_id": self.installation, "token": self.token})
        self.assertTrue(result["ok"])
        push.handle(self.service, "POST", [], {"installation_id": self.installation, "token": self.token + "-rotated"})
        _, result = push.handle(self.service, "GET", [], {})
        self.assertNotIn("token", str(result))
        self.assertEqual(self.con.execute("SELECT count(*) FROM push_devices").fetchone()[0], 1)

    def test_invalid_installation_and_token_are_rejected(self):
        with self.assertRaises(app.ApiError):
            push.handle(self.service, "POST", [], {"installation_id": "bad", "token": self.token})
        with self.assertRaises(app.ApiError):
            push.handle(self.service, "POST", [], {"installation_id": self.installation, "token": "bad\nvalue"})

    def test_enqueues_only_when_provider_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            push.enqueue(self.con, "w1", "n1", "Title", "Body", "q1")
        self.assertEqual(self.con.execute("SELECT count(*) FROM push_outbox").fetchone()[0], 0)
        with patch.dict(os.environ, {"RUSTORE_PUSH_PROJECT_ID": "project-12345678", "RUSTORE_PUSH_SERVICE_TOKEN": "test-service-token"}):
            push.enqueue(self.con, "w1", "n1", "Title", "Body", "q1")
        self.assertEqual(self.con.execute("SELECT count(*) FROM push_outbox").fetchone()[0], 1)

    def test_successful_delivery_marks_event_sent(self):
        with patch.dict(os.environ, {"RUSTORE_PUSH_PROJECT_ID": "project-12345678", "RUSTORE_PUSH_SERVICE_TOKEN": "test-service-token"}):
            push.handle(self.service, "POST", [], {"installation_id": self.installation, "token": self.token})
            push.enqueue(self.con, "w1", "n1", "Смета обновлена", "Откройте Сметру", "q1")
            with patch.object(push, "_send", return_value=(True, 200, False)):
                result = push.run_batch(self.con)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["delivered"], 1)
        self.assertIsNotNone(self.con.execute("SELECT sent_at FROM push_outbox").fetchone()[0])

    def test_transient_failure_uses_backoff(self):
        with patch.dict(os.environ, {"RUSTORE_PUSH_PROJECT_ID": "project-12345678", "RUSTORE_PUSH_SERVICE_TOKEN": "test-service-token"}):
            push.handle(self.service, "POST", [], {"installation_id": self.installation, "token": self.token})
            push.enqueue(self.con, "w1", "n1", "Title", "Body", "q1")
            with patch.object(push, "_send", return_value=(False, 503, False)):
                result = push.run_batch(self.con)
        row = self.con.execute("SELECT attempts,next_attempt_at,sent_at FROM push_outbox").fetchone()
        self.assertEqual(result["processed"], 1)
        self.assertEqual(row["attempts"], 1)
        self.assertIsNone(row["sent_at"])
        self.assertGreater(row["next_attempt_at"], push._now())
    def test_installation_id_uuid_is_strict(self):
        self.assertTrue(push._valid_installation_id(self.installation))
        self.assertFalse(push._valid_installation_id("not-a-uuid"))
        self.assertFalse(push._valid_installation_id("x" * 36))

    def test_cron_requires_a_fresh_signed_one_time_invocation(self):
        secret = "s" * 32
        moment = str(push._now())
        nonce = "a" * 32
        signature = hmac.new(
            secret.encode(),
            ("smetra-push-worker:v1:" + moment + ":" + nonce).encode(),
            hashlib.sha256,
        ).hexdigest()
        with patch.dict(os.environ, {"ASSISTANT_WORKER_SECRET": secret}):
            self.service.h.headers = {"Authorization": f"Bearer v1.{moment}.{nonce}.{signature}"}
            push.authenticate_cron(self.service.h)
            self.service.h.headers = {"Authorization": f"Bearer v1.{moment}.{nonce}." + "0" * 64}
            with self.assertRaises(app.ApiError):
                push.authenticate_cron(self.service.h)
            old_moment = str(push._now() - 600)
            old_signature = hmac.new(
                secret.encode(),
                ("smetra-push-worker:v1:" + old_moment + ":" + nonce).encode(),
                hashlib.sha256,
            ).hexdigest()
            self.service.h.headers = {"Authorization": f"Bearer v1.{old_moment}.{nonce}.{old_signature}"}
            with self.assertRaises(app.ApiError):
                push.authenticate_cron(self.service.h)

    def test_invalid_provider_registration_is_removed(self):
        with patch.dict(os.environ, {"RUSTORE_PUSH_PROJECT_ID": "project-12345678", "RUSTORE_PUSH_SERVICE_TOKEN": "test-service-token"}):
            push.handle(self.service, "POST", [], {"installation_id": self.installation, "token": self.token})
            push.enqueue(self.con, "w1", "n1", "Title", "Body", "q1")
            with patch.object(push, "_send", return_value=(False, 404, True)):
                push.run_batch(self.con)
        self.assertEqual(self.con.execute("SELECT count(*) FROM push_devices").fetchone()[0], 0)
    def test_postgres_translates_push_tables_to_private_schema(self):
        sql = translate(
            "SELECT d.token FROM push_devices d JOIN push_outbox o ON o.id=d.id JOIN push_deliveries p ON p.device_id=d.id",
            "smetra",
        )
        self.assertIn("smetra.push_devices", sql)
        self.assertIn("smetra.push_outbox", sql)
        self.assertIn("smetra.push_deliveries", sql)
    def test_partial_failure_retries_only_failed_devices(self):
        second_installation = "b3b3b3b3-1234-4234-8234-123456789abc"
        second_token = "second-token-value-for-unit-tests-7890"
        with patch.dict(os.environ, {"RUSTORE_PUSH_PROJECT_ID": "project-12345678", "RUSTORE_PUSH_SERVICE_TOKEN": "test-service-token"}):
            push.handle(self.service, "POST", [], {"installation_id": self.installation, "token": self.token})
            other = Service(self.con)
            other.user = {"id": "u2"}
            self.con.execute("INSERT INTO users VALUES('u2')")
            self.con.execute("INSERT INTO workspace_members VALUES('w1','u2','member')")
            self.con.execute("INSERT INTO sessions VALUES('s2','u2','session-hash-2',9999999999)")
            other.h.session_token_hash = "session-hash-2"
            push.handle(other, "POST", [], {"installation_id": second_installation, "token": second_token})
            push.enqueue(self.con, "w1", "n1", "Title", "Body", "q1")
            calls = []
            def partial(token, event):
                calls.append(token)
                return (True, 200, False) if token == self.token else (False, 503, False)
            with patch.object(push, "_send", side_effect=partial):
                push.run_batch(self.con)
            rows = self.con.execute("SELECT d.token,p.sent_at,p.completed_at FROM push_deliveries p JOIN push_devices d ON d.id=p.device_id ORDER BY d.token").fetchall()
            self.assertEqual(len(rows), 2)
            sent = {r["token"]: r["sent_at"] is not None for r in rows}
            self.assertTrue(sent[self.token])
            self.assertFalse(sent[second_token])
            self.con.execute("UPDATE push_deliveries SET next_attempt_at=0 WHERE sent_at IS NULL")
            self.con.execute("UPDATE push_outbox SET next_attempt_at=0 WHERE sent_at IS NULL")
            with patch.object(push, "_send", side_effect=lambda token,event: (True, 200, False)):
                push.run_batch(self.con)
        self.assertEqual(calls.count(self.token), 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM push_deliveries WHERE completed_at IS NULL").fetchone()[0], 0)
        self.assertIsNotNone(self.con.execute("SELECT sent_at FROM push_outbox").fetchone()[0])

    def test_rustore_token_errors_are_distinguished_from_project_errors(self):
        self.assertFalse(push._is_invalid_token_error(404, b'{"error":{"status":"NOT_FOUND","message":"Project not found"}}'))
        self.assertTrue(push._is_invalid_token_error(404, b'{"error":{"status":"NOT_FOUND","message":"Requested entity was not found."}}'))
        self.assertTrue(push._is_invalid_token_error(400, b'{"error":{"status":"INVALID_ARGUMENT","message":"The registration token is not a valid FCM registration token"}}'))
        self.assertFalse(push._is_invalid_token_error(400, b'{"error":{"status":"INVALID_ARGUMENT","message":"Invalid project configuration"}}'))
