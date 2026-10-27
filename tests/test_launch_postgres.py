"""Full API checks on disposable PostgreSQL; providers are controlled local doubles."""
import concurrent.futures
import copy
import hashlib
import json
import os
import secrets
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import psycopg
from backend import app, postgres
from backend.estimate_safety import LEGAL_CONSENT_VERSION

ENABLED = bool(os.getenv("SMETRA_TEST_FULL_POSTGRES") == "1"
               and os.getenv("SMETRA_TEST_ADMIN_URL")
               and os.getenv("SMETRA_TEST_RUNTIME_URL"))


@unittest.skipUnless(ENABLED, "requires the full disposable PostgreSQL API fixture")
class LaunchPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.prepare_test_postgres import validate_target

        validate_target(os.environ["SMETRA_TEST_ADMIN_URL"])
        validate_target(os.environ["SMETRA_TEST_RUNTIME_URL"])
        cls.environment = patch.dict(os.environ, {
            "DATABASE_URL": os.environ["SMETRA_TEST_ADMIN_URL"],
            "RUNTIME_DATABASE_URL": os.environ["SMETRA_TEST_RUNTIME_URL"],
            "SMETRA_LOCAL_POSTGRES": "1", "SMETRA_DB_POOL_MAX": "2",
            "SMETRA_ASSISTANT_DB_POOL_MAX": "2", "REDIS_ENABLED": "off",
            "OPENROUTER_API_KEY": "fixture-only",
            "ASSISTANT_WORKER_SECRET": "fixture-worker-secret-not-used-outside-tests",
            "YOOKASSA_MODE": "live", "YOOKASSA_SHOP_ID": "fixture-shop",
            "YOOKASSA_SECRET_KEY": "fixture-only", "YOOKASSA_MERCHANT_TYPE": "self_employed",
        })
        cls.environment.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://localhost:" + str(cls.server.server_port)
        cls.origin = patch.object(app, "ORIGIN", cls.base)
        cls.origin.start()
        cls.origins = patch.object(app, "BROWSER_ORIGINS", app.BROWSER_ORIGINS | {cls.base})
        cls.origins.start()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.origins.stop()
        cls.origin.stop()
        pools = list(postgres._POOLS.values())
        postgres._POOLS.clear()
        for pool in pools:
            pool.close()
        cls.environment.stop()

    def setUp(self):
        for provider in (
            patch("backend.chat_titles.generate_title", return_value=None),
            patch("backend.mytracker.track_custom_event", return_value=False),
        ):
            provider.start()
            self.addCleanup(provider.stop)

    def account(self):
        user, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as con:
            con.execute(
                "INSERT INTO smetra.users(id,email,password_hash,name,created_at,email_verified_at) "
                "VALUES(%s,%s,'unused','Launch QA',%s,%s)",
                (user, user + "@test.invalid", app.now(), app.now()))
            con.execute("INSERT INTO smetra.sessions(id,user_id,token_hash,expires_at) VALUES(%s,%s,%s,%s)",
                        (str(uuid.uuid4()), user, hashlib.sha256(token.encode()).hexdigest(), app.now() + 3600))
        status, _ = self.request("/me/legal-consent", token, {"accepted": True, "version": LEGAL_CONSENT_VERSION})
        self.assertEqual(status, 200)
        return user, token

    def request(self, path, token=None, body=None, *, method=None, headers=None, raw=False, timeout=15):
        request = urllib.request.Request(
            self.base + "/api" + path,
            json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json",
                     **({"Authorization": "Bearer " + token} if token else {}),
                     **(headers or {})}, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            data = response.read()
            return response.status, data.decode() if raw else json.loads(data)

    def enqueue(self, token, prompt="Проверь данные"):
        status, data = self.request("/assistant/jobs", token, {"text": prompt},
                                    headers={"Idempotency-Key": secrets.token_hex(16)})
        self.assertEqual(status, 202, data)
        return data["job"]["id"]

    def test_live_read_and_stop_work_while_two_models_occupy_assistant_pools(self):
        actors = [self.account() for _ in range(3)]
        jobs = [self.enqueue(token) for _, token in actors[:2]]
        entered, release = threading.Barrier(3), threading.Event()

        def provider(messages, on_delta):
            on_delta("Начало ")
            entered.wait(timeout=10)
            if not release.wait(timeout=12):
                raise AssertionError("Model wait was not released")
            return {"content": "Проверено.", "_usage": {"prompt_tokens": 100, "completion_tokens": 20}}

        with patch("backend.assistant.query_model_stream", side_effect=provider), \
                concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.request, "/assistant/stream", actors[i][1], {"job_id": jobs[i]}, raw=True)
                for i in range(2)]
            try:
                entered.wait(timeout=10)
                started = time.monotonic()
                for path in ("/me", "/dashboard", "/assistant", "/clients", "/quotes"):
                    self.assertEqual(self.request(path, actors[2][1], timeout=3)[0], 200, path)
                status, stopped = self.request("/assistant/jobs/" + jobs[0], actors[0][1], method="DELETE", timeout=3)
                self.assertEqual(status, 200, stopped)
                self.assertTrue(stopped["job"]["cancel_requested"])
                self.assertLess(time.monotonic() - started, 3)
                self.assertFalse(release.is_set())
            finally:
                release.set()
            replies = [future.result(timeout=15) for future in futures]
        self.assertIn("event: error", replies[0][1])
        self.assertIn("event: done", replies[1][1])
        self.assertEqual(self.request("/assistant/jobs/" + jobs[0], actors[0][1])[1]["job"]["status"], "cancelled")
        self.assertEqual(self.request("/assistant", actors[0][1])[1]["messages"], [])
        self.assertEqual(len(self.request("/assistant", actors[1][1])[1]["messages"]), 2)

    def test_real_model_loop_persists_one_answer_and_respects_column_grants(self):
        user, token = self.account()
        job = self.enqueue(token)
        reply = {"content": "Сохранено.", "_usage": {"prompt_tokens": 120, "completion_tokens": 30}}
        with patch("backend.assistant.query_model_stream", return_value=reply) as model:
            status, stream = self.request("/assistant/stream", token, {"job_id": job}, raw=True)
            self.assertEqual(status, 200)
            self.assertIn("event: done", stream)
            charged = self.request("/assistant", token)[1]["quota"]["used"]
            self.assertGreater(charged, 0)
            self.request("/assistant/stream", token, {"job_id": job}, raw=True)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(self.request("/assistant", token)[1]["quota"]["used"], charged)
        with psycopg.connect(os.environ["DATABASE_URL"]) as con:
            permissions = con.execute(
                "SELECT has_table_privilege('smetra_runtime','smetra.assistant_jobs','UPDATE'),"
                "has_column_privilege('smetra_runtime','smetra.assistant_jobs','status','UPDATE'),"
                "has_column_privilege('smetra_runtime','smetra.assistant_jobs','attempts','UPDATE')").fetchone()
            self.assertEqual(permissions, (False, True, False))
            self.assertEqual(con.execute("SELECT count(*) FROM smetra.assistant_messages WHERE user_id=%s", (user,)).fetchone()[0], 2)

    def test_database_pool_exhaustion_is_retryable_without_exposing_configuration(self):
        from psycopg_pool import PoolTimeout

        with patch("backend.postgres._connection_pool", side_effect=PoolTimeout("secret-db-password")):
            status, payload = self.request("/me")
        self.assertEqual(status, 503)
        self.assertEqual(payload["code"], "database_unavailable")
        self.assertEqual(payload["retryAfter"], 5)
        self.assertNotIn("secret-db-password", json.dumps(payload))

    def test_purchase_pending_cancel_renew_refund_and_replay_via_real_api(self):
        user, token = self.account()
        provider_rows, creates = {}, []
        lock = threading.Lock()

        def provider(handler, path, method="GET", payload=None, key=None):
            with lock:
                if method == "POST" and path == "/payments":
                    provider_id = "fixture-" + key
                    if provider_id not in provider_rows:
                        creates.append(provider_id)
                        provider_rows[provider_id] = {
                            "id": provider_id, "test": False, "recipient": {"account_id": "fixture-shop"},
                            "amount": payload["amount"], "metadata": payload["metadata"],
                            "status": "pending", "paid": False,
                            "confirmation": {"confirmation_url": "https://pay.fixture.invalid/" + provider_id},
                        }
                    return copy.deepcopy(provider_rows[provider_id])
                return copy.deepcopy(provider_rows[path.rsplit("/", 1)[-1]])

        def checkout():
            status, body = self.request("/billing/checkout", token, {"plan": "pro_month"},
                                         headers={"Idempotency-Key": secrets.token_hex(16)})
            self.assertEqual(status, 201, body)
            return body["url"].rsplit("/", 1)[-1]

        def notify(payment):
            return self.request("/webhooks/yookassa", body={
                "event": "payment.succeeded", "object": {"id": payment}})

        with patch.object(app.Handler, "provider_call", provider):
            first = checkout()
            self.assertEqual(self.request("/billing/sync", token, {})[1]["user"]["plan"], "free")
            provider_rows[first].update(status="succeeded", paid=True)
            self.assertEqual(notify(first)[0], 200)
            first_until = self.request("/me", token)[1]["user"]["entitlement_until"]
            self.assertGreater(first_until, app.now() + 29 * 86400)
            self.assertEqual(notify(first)[0], 200)
            self.assertEqual(self.request("/me", token)[1]["user"]["entitlement_until"], first_until)
            cancelled = checkout()
            provider_rows[cancelled].update(status="canceled", paid=False)
            self.assertEqual(self.request("/billing/sync", token, {})[0], 200)
            self.assertEqual(self.request("/me", token)[1]["user"]["entitlement_until"], first_until)
            renewed = checkout()
            provider_rows[renewed].update(status="succeeded", paid=True)
            self.assertEqual(notify(renewed)[0], 200)
            self.assertEqual(self.request("/me", token)[1]["user"]["entitlement_until"], first_until + 31 * 86400)
            refund_id = "fixture-refund-" + secrets.token_hex(8)
            provider_rows[refund_id] = {"id": refund_id, "payment_id": renewed,
                                       "amount": provider_rows[renewed]["amount"], "status": "succeeded"}
            event = {"event": "refund.succeeded", "object": {"id": refund_id, "payment_id": renewed}}
            self.assertEqual(self.request("/webhooks/yookassa", body=event)[0], 200)
            self.assertEqual(self.request("/webhooks/yookassa", body=event)[0], 200)
            self.assertEqual(self.request("/me", token)[1]["user"]["entitlement_until"], first_until)
        self.assertEqual(len(creates), 3)
        with psycopg.connect(os.environ["DATABASE_URL"]) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM smetra.payments WHERE user_id=%s", (user,)).fetchone()[0], 3)
            self.assertEqual(con.execute("SELECT count(*) FROM smetra.refunds r JOIN smetra.payments p ON p.id=r.payment_id WHERE p.user_id=%s", (user,)).fetchone()[0], 1)
