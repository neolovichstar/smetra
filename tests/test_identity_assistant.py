import http.client
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from tests.test_business import BusinessFlows
from backend.identity import challenge


class IdentityAssistantTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp
    call = BusinessFlows.call
    account = BusinessFlows.account

    def get_redirect(self, path, cookie=""):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1]
        )
        connection.request("GET", path, headers={"Cookie": cookie})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_provider_list_has_no_external_credentials(self):
        with patch.dict(
            os.environ, YANDEX_CLIENT_ID="test-id", YANDEX_CLIENT_SECRET="never-expose"
        ):
            status, data = self.call("/auth/providers")
            self.assertEqual(status, 200)
            self.assertEqual(
                [p["id"] for p in data["providers"]], ["yandex", "vk", "mail"]
            )
            self.assertNotIn("never-expose", json.dumps(data))

    def test_oauth_browser_binding_and_native_pkce_one_use(self):
        verifier = "a" * 64
        with (
            patch.dict(os.environ, YANDEX_CLIENT_ID="test-id"),
            patch(
                "backend.identity.profile",
                return_value=("unique-subject", "Тестовый вход", "oauth@test.invalid"),
            ) as provider,
        ):
            code, headers, _ = self.get_redirect(
                "/api/auth/oauth/yandex/start?app_challenge=" + challenge(verifier)
            )
            self.assertEqual(code, 303)
            state = parse_qs(urlsplit(headers["Location"]).query)["state"][0]
            cookie = headers["Set-Cookie"].split(";")[0]
            callback = (
                "/api/auth/oauth/yandex/callback?code=provider-code&state=" + state
            )
            code, rejected, _ = self.get_redirect(callback)
            self.assertIn("auth_error=expired", rejected["Location"])
            provider.assert_not_called()
            code, success, _ = self.get_redirect(callback, cookie)
            self.assertTrue(success["Location"].startswith("smetra://auth?ticket="))
            ticket = parse_qs(urlsplit(success["Location"]).query)["ticket"][0]
            self.assertEqual(
                self.call(
                    "/auth/native/exchange",
                    "POST",
                    {"ticket": ticket, "verifier": "b" * 64},
                )[0],
                400,
            )
            status, session = self.call(
                "/auth/native/exchange",
                "POST",
                {"ticket": ticket, "verifier": verifier},
            )
            self.assertEqual(status, 200, session)
            self.assertEqual(session["user"]["name"], "Тестовый вход")
            self.assertEqual(
                self.call(
                    "/auth/native/exchange",
                    "POST",
                    {"ticket": ticket, "verifier": verifier},
                )[0],
                400,
            )
            # Web login through the same provider maps to exactly the same user.
            _, headers, _ = self.get_redirect("/api/auth/oauth/yandex/start")
            state = parse_qs(urlsplit(headers["Location"]).query)["state"][0]
            _, headers, _ = self.get_redirect(
                "/api/auth/oauth/yandex/callback?code=again&state=" + state,
                headers["Set-Cookie"].split(";")[0],
            )
            cookie = headers["Set-Cookie"].split(";")[0]
            status, _, raw = self.get_redirect("/api/me", cookie)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["user"]["id"], session["user"]["id"])

    def test_assistant_proposal_is_scoped_confirmed_and_idempotent(self):
        token, _ = self.account("assistant-owner")
        stranger, _ = self.account("assistant-stranger")
        response = {
            "content": None,
            "tool_calls": [
                {
                    "id": "test-tool",
                    "type": "function",
                    "function": {
                        "name": "create_clients",
                        "arguments": json.dumps({"name": "Студия Север"}),
                    },
                }
            ],
        }
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
            patch("backend.assistant.query_model", return_value=response),
        ):
            status, result = self.call(
                "/assistant/chat",
                "POST",
                {"text": "Добавь клиента Студия Север"},
                token,
            )
        self.assertEqual(status, 200, result)
        action = result["actions"][0]["id"]
        self.assertEqual(self.call("/clients", token=token)[1]["items"], [])
        self.assertEqual(
            self.call("/assistant/confirm", "POST", {"id": action}, stranger)[0], 404
        )
        first = self.call("/assistant/confirm", "POST", {"id": action}, token)
        second = self.call("/assistant/confirm", "POST", {"id": action}, token)
        self.assertEqual(first[0], 200, first)
        self.assertEqual(first, second)
        self.assertEqual(len(self.call("/clients", token=token)[1]["items"]), 1)
        self.assertEqual(self.call("/assistant", token=stranger)[1]["messages"], [])

    def test_assistant_free_only_configuration(self):
        from backend.assistant import query_model
        from backend.business import DomainError

        with (
            patch.dict(os.environ, OPENROUTER_MODEL="paid-model"),
            self.assertRaises(DomainError),
        ):
            query_model([])


if __name__ == "__main__":
    unittest.main()
