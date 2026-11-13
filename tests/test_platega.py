"""Platega migration regression tests, with no live provider calls or secrets."""

import hashlib
import json
import os
import secrets
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch

from backend import platega
import test_flows


class PlategaApiTests(unittest.TestCase):
    setUpClass = classmethod(test_flows.FlowTests.setUpClass.__func__)
    tearDownClass = classmethod(test_flows.FlowTests.tearDownClass.__func__)

    def setUp(self):
        self.user_id = self.mod.uid()
        self.token = secrets.token_urlsafe(32)
        self.transaction_id = str(uuid.uuid4())
        self.merchant_id = str(uuid.uuid4())
        self.env = patch.dict(os.environ, {
            "PAYMENT_PROVIDER": "platega", "PLATEGA_MODE": "live",
            "PLATEGA_MERCHANT_ID": self.merchant_id, "PLATEGA_API_KEY": "fixture-secret",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        with self.mod.db() as con:
            con.execute(
                "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,?,?,?)",
                (self.user_id, self.user_id + "@example.test", "unused", "Плательщик", self.mod.now(), self.mod.now()),
            )
            con.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                        (self.mod.uid(), self.user_id, hashlib.sha256(self.token.encode()).hexdigest(), self.mod.now() + 3600))

    def post(self, path, data, extra=None):
        headers = {"Content-Type": "application/json", **(extra or {})}
        request = urllib.request.Request(self.base + path, json.dumps(data).encode(), headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def checkout(self, plan="pro_month"):
        return self.post("/api/billing/checkout", {"plan": plan}, {
            "Authorization": "Bearer " + self.token, "Idempotency-Key": "fixed-platega-checkout-key-123",
        })

    def test_unconfigured_provider_stops_checkout_without_falling_back_to_yookassa(self):
        with patch.dict(os.environ, {"PLATEGA_MERCHANT_ID": ""}):
            self.assertEqual(self.mod.billing_mode(), "off")
            status, _ = self.checkout()
            self.assertEqual(status, 503)

    def test_subscription_callback_is_authenticated_verified_and_idempotent(self):
        payment = {}
        observed = []

        def provider(handler, path, method="GET", payload=None):
            observed.append((path, method))
            if method == "POST":
                self.assertEqual(payload["metadata"]["userId"], self.user_id)
                self.assertEqual(payload["metadata"]["user_email"], self.user_id + "@example.test")
                self.assertEqual(payload["paymentDetails"], {"amount": 790, "currency": "RUB"})
                payment.update({"payload": payload["payload"], "amount": 790, "status": "PENDING"})
                return {"transactionId": self.transaction_id, "merchantId": self.merchant_id,
                        "status": "PENDING", "url": "https://pay.platega.io/?id=fixture"}
            return {"id": self.transaction_id, "merchantId": self.merchant_id,
                    "status": payment["status"], "payload": payment["payload"],
                    "paymentDetails": {"amount": payment["amount"], "currency": "RUB"}}

        with patch.object(self.mod.Handler, "platega_call", provider), patch("backend.mytracker.track_custom_event"):
            status, result = self.checkout()
            self.assertEqual(status, 201)
            self.assertEqual(result["url"], "https://pay.platega.io/?id=fixture")
            self.assertEqual(self.checkout()[0], 200)
            self.assertEqual(sum(method == "POST" for _, method in observed), 1)
            callback = {"id": self.transaction_id, "status": "CONFIRMED"}
            self.assertEqual(self.post("/api/webhooks/platega", callback)[0], 403)
            invalid = {"X-MerchantId": self.merchant_id, "X-Secret": "fixture-secret-wrong"}
            self.assertEqual(self.post("/api/webhooks/platega", callback, invalid)[0], 403)
            headers = {"X-MerchantId": self.merchant_id, "X-Secret": "fixture-secret"}
            self.assertEqual(self.post("/api/webhooks/platega", callback, headers)[0], 200)
            with self.mod.db() as con:
                self.assertEqual(con.execute("SELECT status FROM payments WHERE user_id=?", (self.user_id,)).fetchone()[0], "pending")
            payment["payload"] = "someone-elses-order"
            payment["status"] = "CONFIRMED"
            self.assertEqual(self.post("/api/webhooks/platega", callback, headers)[0], 409)
            payment["payload"] = self._intent_id()
            payment["amount"] = 1
            self.assertEqual(self.post("/api/webhooks/platega", callback, headers)[0], 409)
            payment["amount"] = 790
            self.assertEqual(self.post("/api/webhooks/platega", callback, headers)[0], 200)
            self.assertEqual(self.post("/api/webhooks/platega", callback, headers)[0], 200)
            with self.mod.db() as con:
                self.assertEqual(con.execute("SELECT status FROM payments WHERE user_id=?", (self.user_id,)).fetchone()[0], "succeeded")
                self.assertEqual(con.execute("SELECT count(*) FROM events WHERE user_id=? AND name='payment_succeeded'", (self.user_id,)).fetchone()[0], 1)
            payment["status"] = "CHARGEBACKED"
            self.assertEqual(self.post("/api/webhooks/platega", {**callback, "status": "CHARGEBACKED"}, headers)[0], 200)
            self.assertEqual(self.post("/api/webhooks/platega", {**callback, "status": "CHARGEBACKED"}, headers)[0], 200)
            with self.mod.db() as con:
                self.assertEqual(con.execute("SELECT count(*) FROM refunds WHERE payment_id IN (SELECT id FROM payments WHERE user_id=?)", (self.user_id,)).fetchone()[0], 1)
                self.assertEqual(con.execute("SELECT plan FROM users WHERE id=?", (self.user_id,)).fetchone()[0], "free")

    def _intent_id(self):
        with self.mod.db() as con:
            return con.execute("SELECT id FROM billing_intents WHERE user_id=?", (self.user_id,)).fetchone()[0]

    def test_pure_validation_rejects_malicious_redirects_and_fractional_kopecks(self):
        self.assertEqual(platega.kopecks(790.25), 79025)
        for amount in (True, float("nan"), -1, "1.001", None):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                platega.kopecks(amount)
        for url in ("http://pay.platega.io", "https://pay.platega.io.evil.test/",
                    "https://user@pay.platega.io/", "https://example.test/pay"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                platega.payment_url(url)

    def test_token_pack_checkout_uses_platega_and_cannot_grant_from_redirect(self):
        transaction_id = str(uuid.uuid4())
        sent = {}

        def provider(handler, path, method="GET", payload=None):
            if method == "POST":
                sent.update(payload)
                return {"transactionId": transaction_id, "status": "PENDING",
                        "merchantId": self.merchant_id, "url": "https://pay.platega.io/pay"}
            return {"id": transaction_id, "status": "PENDING", "payload": sent["payload"],
                    "paymentDetails": sent["paymentDetails"], "merchantId": self.merchant_id}

        with patch.object(self.mod.Handler, "platega_call", provider):
            status, result = self.post("/api/billing/tokens/checkout", {"millions": 1}, {
                "Authorization": "Bearer " + self.token, "Idempotency-Key": "platega-token-pack-idempotent-123",
            })
            self.assertEqual(status, 201)
            self.assertEqual(sent["paymentDetails"], {"amount": 249, "currency": "RUB"})
            self.assertEqual(result["url"], "https://pay.platega.io/pay")
            self.assertEqual(self.post("/api/billing/sync", {}, {"Authorization": "Bearer " + self.token})[0], 200)
            with self.mod.db() as con:
                self.assertEqual(con.execute("SELECT status FROM payments WHERE user_id=?", (self.user_id,)).fetchone()[0], "pending")
                self.assertEqual(con.execute("SELECT count(*) FROM ai_token_ledger WHERE user_id=?", (self.user_id,)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
