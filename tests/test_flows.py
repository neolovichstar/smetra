import importlib.util
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import urllib.parse
from unittest.mock import patch
from pathlib import Path
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]


class FlowTests(unittest.TestCase):
    def test_yookassa_store_gate_rejects_wrong_environment_and_shop(self):
        env = {
            "YOOKASSA_SHOP_ID": "test_shop",
            "YOOKASSA_SECRET_KEY": "test_key",
            "YOOKASSA_MODE": "test",
            "YOOKASSA_MERCHANT_TYPE": "self_employed",
            "YOOKASSA_TEST_EMAIL": "owner@example.test",
        }
        with patch.dict(os.environ, env):
            self.assertEqual(self.mod.yookassa_mode({"email": "stranger@example.test"}), "off")
            self.assertEqual(self.mod.yookassa_mode({"email": "owner@example.test"}), "test")
            valid = {"test": True, "recipient": {"account_id": "test_shop"}}
            self.mod.Handler.verify_yookassa_shop(None, valid)
            with self.assertRaises(self.mod.ApiError):
                self.mod.Handler.verify_yookassa_shop(None, {**valid, "test": False})
            with self.assertRaises(self.mod.ApiError):
                self.mod.Handler.verify_yookassa_shop(None, {**valid, "recipient": {"account_id": "other_shop"}})
        with patch.dict(os.environ, env | {"YOOKASSA_MODE": "live"}):
            self.assertEqual(self.mod.yookassa_mode({"email": "stranger@example.test"}), "live")
            with self.assertRaises(self.mod.ApiError):
                self.mod.Handler.verify_yookassa_shop(None, valid)

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        os.environ["DB_PATH"] = str(Path(cls.temp.name) / "test.sqlite3")
        os.environ["PORT"] = "0"
        spec = importlib.util.spec_from_file_location(
            "smetra_backend", ROOT / "backend" / "app.py"
        )
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        cls.mod.migrate()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.mod.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def request(self, path, method="GET", data=None, token=None):
        payload = json.dumps(data).encode() if data is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(self.base + path, payload, headers, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as r:
            return r.code, json.load(r)

    def test_signup_quote_accept_security_and_billing(self):
        email = "flow@sample.test"
        status, reg = self.request(
            "/api/auth/register",
            "POST",
            {"email": email, "password": "a secure password", "name": "Тест"},
        )
        self.assertEqual(status, 200)
        token = reg["token"]
        status, _ = self.request("/api/admin/overview", token=token)
        self.assertEqual(status, 403)
        status, result = self.request(
            "/api/quotes",
            "POST",
            {
                "title": "Ремонт",
                "client": "Клиент",
                "description": "Состав",
                "amount": 125000,
            },
            token,
        )
        self.assertEqual(status, 201)
        qid = result["quote"]["id"]
        status, _ = self.request(
            "/api/quotes/" + qid + "/status", "POST", {"status": "sent"}, token
        )
        self.assertEqual(status, 200)
        public = result["quote"]["public_url"].split("quote=")[1]
        status, result = self.request("/api/public/quote?token=" + public)
        self.assertEqual(status, 200)
        self.assertEqual(result["quote"]["amount_kopecks"], 125000)
        status, _ = self.request("/api/public/accept", "POST", {"token": public})
        self.assertEqual(status, 200)
        status, _ = self.request("/api/public/accept", "POST", {"token": public})
        self.assertEqual(status, 409)
        status, result = self.request("/api/quotes", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(result["quotes"][0]["status"], "accepted")
        status, _ = self.request(
            "/api/billing/checkout", "POST", {"plan": "pro_month"}, token
        )
        self.assertEqual(status, 400)
        status, _ = self.request("/api/me", "DELETE", {}, token)
        self.assertEqual(status, 200)
        status, _ = self.request("/api/me", token=token)
        self.assertEqual(status, 401)
        with self.mod.db() as con:
            self.assertEqual(
                con.execute(
                    "SELECT count(*) FROM users WHERE email=?", (email,)
                ).fetchone()[0],
                0,
            )

    def test_checkout_idempotency_and_verified_entitlement(self):
        os.environ["YOOKASSA_SHOP_ID"] = "test_shop"
        os.environ["YOOKASSA_SECRET_KEY"] = "test_key"
        os.environ["YOOKASSA_MODE"] = "test"
        os.environ["YOOKASSA_TEST_EMAIL"] = "billing@sample.test"
        os.environ["YOOKASSA_MERCHANT_TYPE"] = "self_employed"
        original = self.mod.Handler.provider_call

        def provider(handler, path, method="GET", payload=None, key=None):
            if method == "POST":
                self.assertNotIn("receipt", payload)
                return {
                    "id": "provider-test-1",
                    "test": True,
                    "recipient": {"account_id": "test_shop"},
                    "confirmation": {
                        "confirmation_url": "https://pay.example.test/checkout"
                    },
                }
            if path.startswith("/refunds/"):
                return {
                    "id": "refund-test-1",
                    "payment_id": "provider-test-1",
                    "status": "succeeded",
                    "amount": {"value": "490.00", "currency": "RUB"},
                }
            return {
                "id": "provider-test-1",
                "test": True,
                "recipient": {"account_id": "test_shop"},
                "status": "succeeded",
                "paid": True,
                "amount": {"value": "490.00", "currency": "RUB"},
                "metadata": {"user_id": self.payment_user, "plan": "pro_month"},
            }

        self.mod.Handler.provider_call = provider
        try:
            status, reg = self.request(
                "/api/auth/register",
                "POST",
                {
                    "email": "billing@sample.test",
                    "password": "secure password twelve",
                    "name": "Биллинг",
                },
            )
            self.assertEqual(status, 200)
            token = reg["token"]
            self.payment_user = reg["user"]["id"]
            key = "a-fixed-unique-key-for-this-test"
            payload = {"plan": "pro_month"}
            for _ in range(2):
                req = urllib.request.Request(
                    self.base + "/api/billing/checkout",
                    json.dumps(payload).encode(),
                    {
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                        "Idempotency-Key": key,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req) as response:
                    self.assertEqual(
                        json.load(response)["url"], "https://pay.example.test/checkout"
                    )
            status, _ = self.request(
                "/api/webhooks/yookassa",
                "POST",
                {"event": "payment.succeeded", "object": {"id": "provider-test-1"}},
            )
            self.assertEqual(status, 200)
            status, _ = self.request(
                "/api/webhooks/yookassa",
                "POST",
                {"event": "payment.succeeded", "object": {"id": "provider-test-1"}},
            )
            self.assertEqual(status, 200)
            status, me = self.request("/api/me", token=token)
            self.assertEqual(me["user"]["plan"], "pro")
            with self.mod.db() as con:
                self.assertEqual(
                    con.execute(
                        "SELECT count(*) FROM payments WHERE user_id=?",
                        (self.payment_user,),
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    con.execute(
                        "SELECT count(*) FROM events WHERE user_id=? AND name='payment_succeeded'",
                        (self.payment_user,),
                    ).fetchone()[0],
                    1,
                )
                con.execute("UPDATE users SET role='admin' WHERE id=?", (self.payment_user,))
            status, overview = self.request("/api/admin/overview", token=token)
            self.assertEqual(status, 200)
            self.assertTrue(any(p["email"] == "billing@sample.test" and p["status"] == "succeeded" for p in overview["payments"]))
            with self.mod.db() as con:
                con.execute("UPDATE users SET role='user' WHERE id=?", (self.payment_user,))
            status, _ = self.request(
                "/api/webhooks/yookassa",
                "POST",
                {"event": "refund.succeeded", "object": {"id": "refund-test-1", "payment_id": "provider-test-1"}},
            )
            self.assertEqual(status, 200)
            status, _ = self.request(
                "/api/webhooks/yookassa",
                "POST",
                {"event": "refund.succeeded", "object": {"id": "refund-test-1", "payment_id": "provider-test-1"}},
            )
            self.assertEqual(status, 200)
            _, me = self.request("/api/me", token=token)
            self.assertEqual(me["user"]["plan"], "free")
            with self.mod.db() as con:
                self.assertEqual(
                    con.execute(
                        "SELECT count(*) FROM refunds WHERE payment_id IN (SELECT id FROM payments WHERE user_id=?)",
                        (self.payment_user,),
                    ).fetchone()[0],
                    1,
                )
            os.environ["YOOKASSA_MODE"] = "off"
            blocked = urllib.request.Request(
                self.base + "/api/billing/checkout",
                json.dumps(payload).encode(),
                {
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                    "Idempotency-Key": key,
                },
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(blocked)
            self.assertEqual(failure.exception.code, 503)
            status, _ = self.request("/api/me", "DELETE", {}, token)
            self.assertEqual(status, 200)
            with self.mod.db() as con:
                self.assertEqual(
                    con.execute(
                        "SELECT count(*) FROM payments WHERE user_id=?",
                        (self.payment_user,),
                    ).fetchone()[0],
                    1,
                )
        finally:
            self.mod.Handler.provider_call = original
            os.environ.pop("YOOKASSA_SHOP_ID", None)
            os.environ.pop("YOOKASSA_SECRET_KEY", None)
            os.environ.pop("YOOKASSA_MODE", None)
            os.environ.pop("YOOKASSA_TEST_EMAIL", None)
            os.environ.pop("YOOKASSA_MERCHANT_TYPE", None)

    def test_password_hash_and_migration(self):
        self.assertTrue(
            self.mod.verify_password(
                "long password!", self.mod.hash_password("long password!")
            )
        )
        self.assertFalse(
            self.mod.verify_password("wrong", self.mod.hash_password("long password!"))
        )
        self.mod.migrate()

    def test_ownership_validation_and_free_limit_after_deletion(self):
        _, first = self.request(
            "/api/auth/register",
            "POST",
            {
                "email": "owner@sample.test",
                "password": "secure password twelve",
                "name": "Владелец",
            },
        )
        _, second = self.request(
            "/api/auth/register",
            "POST",
            {
                "email": "other@sample.test",
                "password": "secure password twelve",
                "name": "Другой",
            },
        )
        payload = {
            "title": "Монтаж",
            "client": "Компания",
            "description": "Объём",
            "amount": 120000,
        }
        created = []
        for _ in range(10):
            status, result = self.request(
                "/api/quotes", "POST", payload, first["token"]
            )
            self.assertEqual(status, 201)
            created.append(result["quote"]["id"])
        status, _ = self.request(
            "/api/quotes/" + created[0], "DELETE", {}, second["token"]
        )
        self.assertEqual(status, 404)
        status, _ = self.request(
            "/api/quotes/" + created[0], "DELETE", {}, first["token"]
        )
        self.assertEqual(status, 200)
        status, _ = self.request("/api/quotes", "POST", payload, first["token"])
        self.assertEqual(status, 402)
        status, _ = self.request(
            "/api/quotes",
            "POST",
            {"title": "x", "client": "y", "amount": -100},
            second["token"],
        )
        self.assertEqual(status, 400)
        status, _ = self.request("/api/quotes?offset=bad", token=first["token"])
        self.assertEqual(status, 400)

    def test_email_verification_and_password_recovery(self):
        messages = []
        old_mail = self.mod.mail
        self.mod.mail = lambda address, subject, body: messages.append(body)
        os.environ["SMTP_HOST"] = "test.smtp.invalid"
        try:
            _, registered = self.request(
                "/api/auth/register",
                "POST",
                {
                    "email": "verify@sample.test",
                    "password": "old password secure",
                    "name": "Проверка",
                },
            )
            self.assertFalse(registered["user"]["email_verified"])
            self.assertEqual(len(messages), 1)
            token = urllib.parse.parse_qs(urllib.parse.urlsplit(messages[-1]).query)[
                "verify"
            ][0]
            status, _ = self.request("/api/auth/verify", "POST", {"token": token})
            self.assertEqual(status, 200)
            status, _ = self.request("/api/auth/verify", "POST", {"token": token})
            self.assertEqual(status, 400)
            _, current = self.request("/api/me", token=registered["token"])
            self.assertTrue(current["user"]["email_verified"])
            status, _ = self.request(
                "/api/auth/reset/request", "POST", {"email": "verify@sample.test"}
            )
            self.assertEqual(status, 200)
            reset = urllib.parse.parse_qs(urllib.parse.urlsplit(messages[-1]).query)[
                "reset"
            ][0]
            status, _ = self.request(
                "/api/auth/reset/confirm",
                "POST",
                {"token": reset, "password": "new password secure"},
            )
            self.assertEqual(status, 200)
            status, _ = self.request("/api/me", token=registered["token"])
            self.assertEqual(status, 401)
            status, _ = self.request(
                "/api/auth/login",
                "POST",
                {"email": "verify@sample.test", "password": "new password secure"},
            )
            self.assertEqual(status, 200)
        finally:
            self.mod.mail = old_mail
            os.environ.pop("SMTP_HOST", None)


if __name__ == "__main__":
    unittest.main()
