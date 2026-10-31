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

    def test_mobile_compat_is_public_and_bounded(self):
        with patch.object(self.mod, "db", side_effect=AssertionError("database opened")), patch.dict(
            os.environ, {"ANDROID_MIN_VERSION_CODE": "40", "ANDROID_LATEST_VERSION_CODE": "bad", "ANDROID_UPDATE_MESSAGE": "x" * 500}
        ):
            status, _, result = self.request("GET", "/api/mobile/compat")
        self.assertEqual(status, 200)
        self.assertEqual(result["bridge_protocol"], 1)
        self.assertEqual(result["min_version_code"], 40)
        self.assertEqual(result["latest_version_code"], 41)
        self.assertEqual(len(result["message"]), 300)
        self.assertTrue(result["store_url"].startswith("https://www.rustore.ru/"))

    def test_browser_cookie_session_requires_same_origin_for_writes(self):
        body = json.dumps({
            "name": "Browser", "email": "browser-security@test.invalid",
            "password": "secure twelve password",
            "legal_acceptance": True,
            "legal_version": "2026-10-19-registration-v1",
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

    def test_canonical_site_and_legacy_alias_are_trusted_without_leaking_session(self):
        # PUBLIC_ORIGIN may reference a legacy Vercel hostname, but the
        # production website uses the canonical domain.
        registration={
            "email":"canonical-origin@test.invalid","name":"Canonical",
            "password":"secure twelve password","legal_acceptance":True,
            "legal_version":"2026-10-19-registration-v1",
        }
        for index, browser_origin in enumerate(
            ("https://smetra.online","https://www.smetra.online",
             "https://smetra.vercel.app")
        ):
            payload=dict(registration,email=f"canonical-origin-{index}@test.invalid")
            status, headers, response=self.request(
                "POST", "/api/auth/register",json.dumps(payload).encode(),
                {"Content-Type":"application/json", "Origin":browser_origin,
                 "Sec-Fetch-Site":"same-site" if index else "same-origin"},
            )
            self.assertEqual(status, 200, response)
            self.assertNotIn("token", response, "Browser session token must stay HttpOnly")
            session=headers["Set-Cookie"].split(";",1)[0]
            status, _, response=self.request("POST","/api/auth/logout",headers={
                "Origin":browser_origin,"Sec-Fetch-Site":"same-site",
                "Cookie":session,
            })
            self.assertEqual(status,200,response)

    def test_email_code_can_be_requested_from_production_origin(self):
        payload=json.dumps({
            "email":"canonical-email-otp@test.invalid","intent":"register",
            "name":"Проверка","legal_acceptance":True,
            "legal_version":"2026-10-19-registration-v1",
        }).encode()
        with patch.dict(os.environ, {
            "SMTP_HOST":"smtp.mail.ru","SMTP_PORT":"465",
            "SMTP_FROM":"noreply@smetra.online",
            "SMTP_USER":"noreply@smetra.online",
            "SMTP_PASSWORD":"fixture-only-no-network",
            "EMAIL_CODE_HMAC_SECRET":"fixture-test-hmac-secret-abcdefghijklmnopqrstuvwxyz",
        }), patch("backend.email_otp.deliver") as delivery:
            status,_,result=self.request(
                "POST","/api/auth/email/start",payload,{
                    "Content-Type":"application/json",
                    "Origin":"https://smetra.online",
                    "Sec-Fetch-Site":"same-origin",
                },
            )
        self.assertEqual(status,200,result)
        self.assertIn("challenge_id",result)
        delivery.assert_called_once()

    def test_cross_site_and_spoofed_origins_are_rejected(self):
        body=b'{"email":"attacker@test.invalid","password":"secure password"}'
        for origin,fetch_site in (
            ("https://attacker.example","cross-site"),
            ("https://smetra.online.attacker.example","same-site"),
            ("http://smetra.online","same-site"),
            ("https://smetra.online/","same-site"),
            (None,"same-site"),
            ("https://smetra.online","cross-site"),
        ):
            headers={"Content-Type":"application/json",
                     "Sec-Fetch-Site":fetch_site}
            if origin:
                headers["Origin"] = origin
            with self.subTest(origin=origin,fetch_site=fetch_site):
                status,_,_ = self.request("POST","/api/auth/login",body,headers)
                self.assertEqual(status,403)

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

    def test_baseline_security_headers_apply_to_errors(self):
        status, headers, result = self.request("GET", "/api/me")
        self.assertEqual(status, 401, result)
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("Referrer-Policy"), "no-referrer")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn("Server", headers)

    def test_response_header_injection_fails_closed(self):
        request = Handler.__new__(Handler)
        request._headers_buffer = []
        with self.assertRaises(ValueError):
            request.send_header(
                "Content-Disposition",
                'attachment; filename="estimate\r\nSet-Cookie: injected=1"',
            )
        with self.assertRaises(ValueError):
            request.send_header("X-Test\r\nInjected", "value")
        self.assertEqual(request._headers_buffer, [])

    def test_local_sensitive_html_is_not_cached(self):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        try:
            connection.request("GET", "/app")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
            self.assertIsNone(response.getheader("Server"))
            response.read()
        finally:
            connection.close()

    def test_cookie_security_defaults(self):
        request = Handler.__new__(Handler)
        with patch.object(self.mod, "COOKIE_SECURE", True):
            cookie = request.cookie("safe-token", 3600)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("; Secure", cookie)
        self.assertIn("; Path=/", cookie)
        self.assertNotIn("Domain=", cookie)
