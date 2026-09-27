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
