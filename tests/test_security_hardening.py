"""Regression checks for the browser/API trust boundary."""

import http.client
import json
import os
import unittest
from unittest.mock import patch

from api.index import handler
from backend.app import Handler
from tests.test_business import BusinessFlows


class SecurityHardeningTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), json.loads(response.read())
        connection.close()
        return result

    def test_json_media_type_and_duplicate_keys(self):
        body = b'{"name":"A","name":"B"}'
        status, _, _ = self.request(
            "POST", "/api/auth/register", body,
            {"Content-Type": "text/plain"},
        )
        self.assertEqual(status, 415)
        status, _, _ = self.request(
            "POST", "/api/auth/register", body,
            {"Content-Type": "application/json; charset=utf-8"},
        )
        self.assertEqual(status, 400)

    def test_large_or_ambiguous_body_is_rejected_before_database(self):
        with patch.object(self.mod, "db", side_effect=AssertionError("database opened")):
            status, _, _ = self.request(
                "POST", "/api/auth/login", headers={"Content-Length": "65537"}
            )
            self.assertEqual(status, 413)
            status, _, _ = self.request(
                "POST", "/api/auth/login", headers={"Content-Length": "abc"}
            )
            self.assertEqual(status, 400)
            status, _, _ = self.request(
                "GET", "/api/me?" + "x" * 4096
            )
            self.assertEqual(status, 414)
            status, _, _ = self.request("GET", "/api/not-a-route")
            self.assertEqual(status, 404)

    def test_unknown_refund_never_calls_payment_provider(self):
        with patch.dict(os.environ, YOOKASSA_MODE="live", YOOKASSA_SHOP_ID="test", YOOKASSA_SECRET_KEY="test", YOOKASSA_MERCHANT_TYPE="self_employed"):
            with patch.object(Handler, "provider_call", side_effect=AssertionError("provider called")):
                status, _, _ = self.request(
                    "POST", "/api/webhooks/yookassa",
                    body=json.dumps({"event": "refund.succeeded", "object": {"id": "fake", "payment_id": "unknown"}}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(status, 404)

    def test_public_provider_list_does_not_open_database(self):
        with patch.object(self.mod, "db", side_effect=AssertionError("database opened")):
            status, _, result = self.request("GET", "/api/auth/providers")
        self.assertEqual(status, 200)
        self.assertIn("providers", result)

    def test_native_presentation_is_public_and_does_not_open_database(self):
        with patch.object(self.mod, "db", side_effect=AssertionError("database opened")):
            status, headers, result = self.request("GET", "/api/mobile/presentation")
            unknown, _, _ = self.request("GET", "/api/mobile/unknown")
        self.assertEqual(status, 200)
        self.assertEqual(unknown, 404)
        self.assertEqual(result["schema"], 1)
        self.assertIn("home", result)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_browser_cookie_session_requires_same_origin_for_writes(self):
        body = json.dumps({
            "name": "Browser", "email": "browser-security@test.invalid",
            "password": "secure twelve password",
        }).encode()
        status, headers, result = self.request(
            "POST", "/api/auth/register", body,
            {"Content-Type": "application/json", "Origin": self.mod.ORIGIN},
        )
        self.assertEqual(status, 200, result)
        self.assertNotIn("token", result)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, _ = self.request(
            "POST", "/api/auth/logout", headers={"Cookie": cookie}
        )
        self.assertEqual(status, 403)
        status, _, _ = self.request("GET", "/api/me", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        status, _, _ = self.request(
            "POST", "/api/auth/logout",
            headers={"Cookie": cookie, "Origin": self.mod.ORIGIN},
        )
        self.assertEqual(status, 200)

    def test_vercel_client_ip_uses_platform_forwarded_header(self):
        request = handler.__new__(handler)
        request.client_address = ("127.0.0.1", 0)
        request.headers = {
            "x-forwarded-for": "198.51.100.7",
            "x-vercel-forwarded-for": "203.0.113.9",
        }
        with patch.dict(os.environ, VERCEL="1"), patch.object(
            Handler, "dispatch", return_value=None
        ):
            request.dispatch("GET")
        self.assertEqual(request.client_address[0], "198.51.100.7")
