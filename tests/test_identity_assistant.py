import http.client
import json
import os
import contextlib
import base64
import sqlite3
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from tests.test_business import BusinessFlows
from backend.identity import challenge


class IdentityAssistantTests(unittest.TestCase):
    def test_assistant_construction_action_needs_confirmation_and_stays_scoped(self):
        token, _ = self.account('construction-ai-owner')
        stranger, _ = self.account('construction-ai-stranger')
        _, created = self.call('/construction/objects', 'POST', {'name': 'Квартира'}, token)
        object_id = created['object']['id']
        tool_call = {'content': None, 'tool_calls': [{
            'id': 'construction-tool', 'type': 'function', 'function': {
                'name': 'create_construction_zone',
                'arguments': json.dumps({'object_id': object_id, 'name': 'Кухня', 'length': '5', 'width': '4'}),
            },
        }]}
        with patch.dict(os.environ, OPENROUTER_API_KEY='test-not-real'), patch('backend.assistant.query_model', return_value=tool_call):
            status, result = self.call('/assistant/chat', 'POST', {'text': 'Добавь кухню 5 на 4'}, token)
        self.assertEqual(status, 200, result)
        action_id = result['actions'][0]['id']
        self.assertEqual(self.call('/construction/objects/' + object_id, token=token)[1]['zones'], [])
        self.assertEqual(self.call('/assistant/confirm', 'POST', {'id': action_id}, stranger)[0], 404)
        first = self.call('/assistant/confirm', 'POST', {'id': action_id}, token)
        second = self.call('/assistant/confirm', 'POST', {'id': action_id}, token)
        self.assertEqual(first, second)
        self.assertEqual(len(self.call('/construction/objects/' + object_id, token=token)[1]['zones']), 1)

    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp
    call = BusinessFlows.call
    account = BusinessFlows.account

    def test_explicit_ai_context_is_scoped_and_minimal(self):
        owner, _ = self.account("context-owner")
        stranger, _ = self.account("context-stranger")
        status, result = self.call(
            "/clients", "POST", {"name": "Студия Север", "notes": "Личные заметки клиента"}, owner
        )
        self.assertEqual(status, 201, result)
        client_id = result["item"]["id"]
        context = {"entity": "clients", "id": client_id}
        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"):
            status, _ = self.call("/assistant/chat", "POST", {"text": "Что дальше?", "context": context}, stranger)
            self.assertEqual(status, 404)
            self.assertEqual(self.call("/assistant", token=stranger)[1]["quota"]["used"], 0)
            with patch("backend.assistant.query_model", return_value={"content": "Проверю клиента."}) as provider:
                status, _ = self.call("/assistant/chat", "POST", {"text": "Что дальше?", "context": context}, owner)
        self.assertEqual(status, 200)
        prompt = provider.call_args.args[0][0]["content"]
        self.assertIn(client_id, prompt)
        self.assertNotIn("Личные заметки клиента", prompt)

    def test_assistant_reads_only_selected_workspace_file_with_page_source(self):
        owner, _ = self.account("file-ai-owner")
        stranger, _ = self.account("file-ai-stranger")
        quote = BusinessFlows.quote(self, owner, title="Файл для AI")
        file_result = self.call(
            "/files", "POST",
            {"quote_id": quote["id"], "name": "brief.txt",
             "content": base64.b64encode("Гарантия 12 месяцев API_KEY=abcdefghijklmnop".encode()).decode()},
            owner,
        )[1]
        file_id = file_result["file"]["id"]
        context = {"entity": "files", "id": file_id}
        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"):
            self.assertEqual(
                self.call("/assistant/chat", "POST", {"text": "Срок гарантии?", "context": context}, stranger)[0],
                404,
            )
            calls = []

            def provider(messages):
                calls.append(messages)
                if len(calls) == 1:
                    return {"tool_calls": [{"id": "read-1", "type": "function", "function": {
                        "name": "read_file", "arguments": json.dumps({"id": file_id, "query": "Гарантия"})
                    }}]}
                return {"content": "В brief.txt, стр. 1: гарантия 12 месяцев."}

            with patch("backend.assistant.query_model", side_effect=provider):
                status, result = self.call(
                    "/assistant/chat", "POST", {"text": "Срок гарантии?", "context": context}, owner
                )
        self.assertEqual(status, 200, result)
        self.assertIn(file_id, calls[0][0]["content"])
        self.assertNotIn("Гарантия 12 месяцев", calls[0][0]["content"])
        source = json.loads(calls[1][-1]["content"])
        self.assertEqual(source["file_id"], file_id)
        self.assertEqual(source["excerpts"][0]["page"], 1)
        self.assertIn("Гарантия 12 месяцев", source["excerpts"][0]["text"])
        self.assertNotIn("abcdefghijklmnop", source["excerpts"][0]["text"])
        self.assertIn("[секрет скрыт]", source["excerpts"][0]["text"])
        self.assertEqual(result["actions"], [])

    def test_file_search_tool_stays_in_workspace(self):
        owner, owner_id = self.account("file-search-owner")
        stranger, stranger_id = self.account("file-search-stranger")
        self.call("/dashboard", token=stranger)
        quote = BusinessFlows.quote(self, owner)
        self.call(
            "/files", "POST",
            {"quote_id": quote["id"], "name": "private-brief.txt",
             "content": base64.b64encode(b"private content").decode()},
            owner,
        )
        from backend.assistant_files import list_files
        from types import SimpleNamespace

        with self.mod.db() as con:
            wid = con.execute("SELECT id FROM workspaces WHERE owner_id=?", (stranger_id,)).fetchone()
            stranger_user=con.execute("SELECT * FROM users WHERE id=?",(stranger_id,)).fetchone()
            service = SimpleNamespace(con=con, wid=wid["id"], user=stranger_user)
            self.assertEqual(list_files(service, "brief"), {"files": []})
            owner_wid = con.execute("SELECT id FROM workspaces WHERE owner_id=?", (owner_id,)).fetchone()
            service.wid = owner_wid["id"]
            service.user=con.execute("SELECT * FROM users WHERE id=?",(owner_id,)).fetchone()
            self.assertEqual([item["name"] for item in list_files(service, "brief")["files"]],
                             ["private-brief.txt"])

    def test_knowledge_rules_and_conversations_are_scoped(self):
        owner, _ = self.account("knowledge-owner")
        outsider, _ = self.account("knowledge-outsider")
        code, created = self.call(
            "/assistant/knowledge", "POST",
            {"title": "Правило расчёта", "content": "Не добавлять НДС без просьбы", "kind": "rule"}, owner,
        )
        self.assertEqual(code, 201, created)
        knowledge_id = created["item"]["id"]
        self.assertEqual(self.call("/assistant/knowledge/" + knowledge_id, token=outsider)[0], 404)
        self.assertEqual(self.call("/assistant/knowledge", token=outsider)[1]["items"], [])
        code, created = self.call(
            "/assistant/conversations", "POST", {"title": "Заказы сегодня"}, owner,
        )
        self.assertEqual(code, 201, created)
        conversation_id = created["conversation"]["id"]
        self.assertEqual(self.call("/assistant/conversations/" + conversation_id, token=outsider)[0], 404)
        with (patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
              patch("backend.assistant.query_model", return_value={"content": "Проверю заказы."}) as provider):
            code, _ = self.call(
                "/assistant/chat", "POST", {"text": "Что с заказами?", "conversation_id": conversation_id}, owner,
            )
        self.assertEqual(code, 200)
        self.assertIn("Не добавлять НДС", provider.call_args.args[0][1]["content"])
        messages = self.call("/assistant/conversations/" + conversation_id, token=owner)[1]["messages"]
        self.assertEqual([item["role"] for item in messages], ["user", "assistant"])
        self.assertEqual(self.call("/assistant/conversations/" + conversation_id + "/fork", "POST",
                                   {"message_id": messages[0]["id"]}, outsider)[0], 404)
        self.assertEqual(self.call("/assistant/conversations/" + conversation_id + "/fork", "POST",
                                   {"message_id": "missing"}, owner)[0], 404)
        code, forked = self.call("/assistant/conversations/" + conversation_id + "/fork", "POST",
                                 {"message_id": messages[0]["id"]}, owner)
        self.assertEqual(code, 201, forked)
        self.assertEqual(forked["copied_messages"], 1)
        branch_id = forked["conversation"]["id"]
        branch_messages = self.call("/assistant/conversations/" + branch_id, token=owner)[1]["messages"]
        self.assertEqual([item["content"] for item in branch_messages], [messages[0]["content"]])
        self.assertEqual(self.call("/assistant", token=owner)[1]["messages"], [])
        self.assertEqual(self.call("/assistant/conversations/" + conversation_id, "PATCH",
                                   {"title": "Важные заказы", "pinned": 1}, owner)[0], 200)
        self.assertEqual(self.call("/assistant/conversations/" + conversation_id, "DELETE", token=owner)[0], 200)
        self.assertEqual(self.call("/assistant/conversations/" + conversation_id, token=owner)[0], 404)
        self.assertEqual(self.call("/assistant/conversations/" + branch_id, token=owner)[0], 200)

    def test_uploaded_text_is_searchable_with_workspace_and_page(self):
        owner, _ = self.account("indexed-file-owner")
        outsider, _ = self.account("indexed-file-outsider")
        quote = BusinessFlows.quote(self, owner)
        code, uploaded = self.call(
            "/files", "POST", {"quote_id": quote["id"], "name": "scope.txt",
            "content": base64.b64encode("Срок гарантии 24 месяца".encode()).decode()}, owner,
        )
        self.assertEqual(code, 201, uploaded)
        found = self.call("/search?q=24", token=owner)[1]["items"]
        self.assertTrue(any(item.get("kind") == "file" and item.get("page") == 1 for item in found))
        self.assertFalse(self.call("/search?q=24", token=outsider)[1]["items"])

    def get_redirect(self, path, cookie="", host=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1]
        )
        headers = {"Cookie": cookie}
        if host is not None:
            headers["Host"] = host
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_yandex_avatar_claim_is_propagated_without_trusting_picture_urls(self):
        from backend.identity import profile
        from backend.app import user_view
        avatar = {"id": "1000034426", "display_name": "Кирилл",
                  "default_email": "kirill@example.test",
                  "default_avatar_id": "131652443",
                  "is_avatar_empty": False}
        token = {"access_token": "test-token"}
        with patch.dict(os.environ, YANDEX_CLIENT_ID="test-client"), patch(
            "backend.identity.remote", side_effect=[token, avatar]
        ):
            subject, name, email, avatar_id = profile(
                "yandex", "test-code", "test-state", "test-verifier",
                "https://smetra.online/api/auth/oauth/yandex/callback", "",
            )
        self.assertEqual((subject, name, email, avatar_id),
                         ("1000034426", "Кирилл", "kirill@example.test", "131652443"))
        with self.mod.db() as con:
            row = con.execute("SELECT * FROM users LIMIT 1").fetchone()
            if row:
                con.execute("UPDATE users SET avatar_id=? WHERE id=?", (avatar_id, row["id"]))
                updated = con.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
                self.assertEqual(
                    user_view(updated, con)["avatar_url"],
                    "https://avatars.yandex.net/get-yapic/131652443/islands-200",
                )

    def test_yandex_avatar_missing_uses_initials(self):
        from backend.identity import profile
        with patch.dict(os.environ, YANDEX_CLIENT_ID="test-client"), patch(
            "backend.identity.remote",
            side_effect=[{"access_token": "test-token"}, {
                "id": "123", "display_name": "Олег",
                "is_avatar_empty": True, "default_avatar_id": "123"
            }],
        ):
            self.assertEqual(
                profile("yandex", "code", "state", "verifier",
                        "https://smetra.online/api/auth/oauth/yandex/callback", "")[3], ""
            )

    def test_yandex_callback_stays_on_verified_start_host(self):
        with patch.dict(os.environ, YANDEX_CLIENT_ID="test-id"):
            status, headers, _ = self.get_redirect(
                "/api/auth/oauth/yandex/start?intent=login", host="smetra.online"
            )
            self.assertEqual(status, 303)
            params = parse_qs(urlsplit(headers["Location"]).query)
            self.assertEqual(
                params["redirect_uri"],
                ["https://smetra.online/api/auth/oauth/yandex/callback"],
            )
            self.assertIn("smetra_oauth=", headers["Set-Cookie"])
            status, headers, _ = self.get_redirect(
                "/api/auth/oauth/yandex/start?intent=login", host="www.smetra.online"
            )
            self.assertEqual(status, 303)
            self.assertEqual(
                headers["Location"],
                "https://smetra.online/api/auth/oauth/yandex/start?intent=login",
            )

    def test_provider_list_has_no_external_credentials(self):
        with patch.dict(
            os.environ, YANDEX_CLIENT_ID="test-id", YANDEX_CLIENT_SECRET="never-expose"
        ):
            status, data = self.call("/auth/providers")
            self.assertEqual(status, 200)
            self.assertEqual(
                [p["id"] for p in data["providers"]], ["yandex", "vk", "mail", "ok"]
            )
            self.assertNotIn("never-expose", json.dumps(data))

    def test_email_delivery_capability_requires_complete_configuration(self):
        values = dict(SMTP_HOST="", SMTP_FROM="", SMTP_USER="", SMTP_PASSWORD="", EMAIL_CODE_HMAC_SECRET="")
        with patch.dict(os.environ, values):
            self.assertFalse(self.call("/auth/providers")[1]["email_delivery_available"])
        values.update(SMTP_HOST="smtp.example.test", SMTP_FROM="support@example.test", SMTP_USER="qa", SMTP_PASSWORD="fixture-private", EMAIL_CODE_HMAC_SECRET="fixture-secret-abcdefghijklmnopqrstuvwxyz-123456")
        with patch.dict(os.environ, values):
            data = self.call("/auth/providers")[1]
            self.assertTrue(data["email_delivery_available"])
            self.assertNotIn("fixture-private", json.dumps(data))
        values["SMTP_PASSWORD"] = ""
        with patch.dict(os.environ, values):
            self.assertFalse(self.call("/auth/providers")[1]["email_delivery_available"])

    def test_email_signup_capability_matches_production_delivery(self):
        values = dict(PUBLIC_ORIGIN="https://example.test", ALLOW_UNVERIFIED_SIGNUP="", SMTP_HOST="", SMTP_FROM="", SMTP_USER="", SMTP_PASSWORD="", EMAIL_CODE_HMAC_SECRET="")
        with patch.dict(os.environ, values):
            self.assertFalse(self.call("/auth/providers")[1]["email_signup_available"])
        values["PUBLIC_ORIGIN"] = "http://localhost:8080"
        with patch.dict(os.environ, values):
            # Localhost is not sufficient to bypass verified email OTP.
            self.assertFalse(self.call("/auth/providers")[1]["email_signup_available"])
        values.update(PUBLIC_ORIGIN="https://example.test", SMTP_HOST="smtp.example.test", SMTP_FROM="support@example.test", SMTP_USER="qa", SMTP_PASSWORD="fixture-private", EMAIL_CODE_HMAC_SECRET="fixture-secret-abcdefghijklmnopqrstuvwxyz-123456")
        with patch.dict(os.environ, values):
            self.assertTrue(self.call("/auth/providers")[1]["email_signup_available"])

    def test_vk_family_uses_server_callback_and_pkce(self):
        with patch.dict(os.environ, VK_CLIENT_ID="54792875"):
            for provider, expected in (("vk", "vkid"), ("mail", "mail_ru"), ("ok", "ok_ru")):
                with self.subTest(provider=provider):
                    code, headers, _ = self.get_redirect(f"/api/auth/oauth/{provider}/start")
                    self.assertEqual(code, 303)
                    target = urlsplit(headers["Location"])
                    params = parse_qs(target.query)
                    self.assertEqual(target.netloc, "id.vk.com")
                    self.assertEqual(params["client_id"], ["54792875"])
                    self.assertEqual(params["provider"], [expected])
                    self.assertEqual(params["redirect_uri"], [f"{self.mod.ORIGIN}/api/auth/oauth/{provider}/callback"])
                    self.assertEqual(params["code_challenge_method"], ["s256"])
                    self.assertEqual(len(params["code_challenge"][0]), 43)
                    self.assertIn("HttpOnly", headers["Set-Cookie"])

    def test_oauth_cannot_create_new_account_without_registration_consent(self):
        with patch.dict(os.environ, YANDEX_CLIENT_ID="test-id"):
            status, headers, _ = self.get_redirect("/api/auth/oauth/yandex/start?intent=register")
            self.assertEqual(status, 303)
            self.assertIn("auth_error=registration_consent_required", headers["Location"])

            status, headers, _ = self.get_redirect(
                "/api/auth/oauth/yandex/start?intent=register&legal_acceptance=1"
                "&legal_version=outdated"
            )
            self.assertEqual(status, 303)
            self.assertIn("auth_error=registration_consent_required", headers["Location"])

            status, headers, _ = self.get_redirect(
                "/api/auth/oauth/yandex/start?intent=register&legal_acceptance=1"
                "&legal_version=2026-10-19-registration-v1"
            )
            self.assertEqual(status, 303)
            state = parse_qs(urlsplit(headers["Location"]).query)["state"][0]
            cookie = headers["Set-Cookie"].split(";")[0]

            with patch(
                "backend.identity.profile",
                return_value=("new-consent-subject", "OAuth без согласия", "oauth-consent@test.invalid"),
            ):
                status, response, _ = self.get_redirect(
                    "/api/auth/oauth/yandex/callback?code=provider-code&state=" + state,
                    cookie,
                )
            self.assertTrue(response["Location"].endswith("/app?auth_error=registration_consent_required") is False)
            self.assertEqual(status, 303)
            with self.mod.db() as con:
                account = con.execute(
                    "SELECT id FROM users WHERE email=?",
                    ("oauth-consent@test.invalid",),
                ).fetchone()
                self.assertIsNotNone(account)
                accepted = con.execute(
                    "SELECT document_version,source FROM legal_acceptances WHERE user_id=?",
                    (account["id"],),
                ).fetchall()
            self.assertEqual(
                [(row["document_version"], row["source"]) for row in accepted],
                [("2026-10-19-registration-v1", "registration")],
            )

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
                "/api/auth/oauth/yandex/start?app_challenge=" + challenge(verifier) + "&intent=register&legal_acceptance=1&legal_version=2026-10-19-registration-v1"
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

    def test_quote_draft_without_client_is_created_and_remains_openable(self):
        owner, _ = self.account("assistant-quote-no-client")
        stranger, _ = self.account("assistant-quote-stranger")
        response = {
            "content": None,
            "tool_calls": [{
                "id": "draft-kitchen", "type": "function",
                "function": {
                    "name": "create_quotes",
                    "arguments": json.dumps({
                        "title": "Ремонт кухни",
                        "items": [{
                            "name": "Грунтовка стен",
                            "quantity": "1", "unit": "м²",
                            "unit_price": 0,
                        }],
                    }),
                },
            }],
        }
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
            patch("backend.assistant.query_model", return_value=response),
        ):
            status, proposed = self.call("/assistant/chat", "POST", {"text": "Составь смету кухни"}, owner)
        self.assertEqual(status, 200, proposed)
        action = proposed["actions"][0]
        self.assertEqual(action["arguments"]["client"], "Клиент не указан")
        # Pending actions created by an older release lack the client field.
        # They must remain applicable after the backend-only hotfix.
        with self.mod.db() as con:
            stored = con.execute(
                "SELECT arguments FROM assistant_actions WHERE id=?", (action["id"],)
            ).fetchone()
            legacy = json.loads(stored["arguments"])
            legacy.pop("client", None)
            con.execute(
                "UPDATE assistant_actions SET arguments=? WHERE id=?",
                (json.dumps(legacy), action["id"]),
            )
        self.assertEqual(self.call("/quotes", token=owner)[1]["quotes"], [])
        rejected = self.call("/assistant/confirm", "POST", {"id": action["id"]}, stranger)
        self.assertEqual(rejected[0], 404)
        status, applied = self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)
        self.assertEqual(status, 200, applied)
        quote = applied["result"]["quote"]
        self.assertEqual(quote["title"], "Ремонт кухни")
        self.assertEqual(quote["client"], "Клиент не указан")
        self.assertEqual(quote["status"], "draft")
        self.assertEqual(quote["amount_kopecks"], 0)
        self.assertEqual(self.call("/quotes/" + quote["id"] + "/publish", "POST", {
            "revision": quote["revision"], "review_confirmed": True,
        }, owner)[0], 409, "Unknown prices must never become a published client offer")
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)[0], 200)
        self.assertEqual(len(self.call("/quotes", token=owner)[1]["quotes"]), 1)
        recent = self.call("/assistant", token=owner)[1]["recent_actions"]
        self.assertTrue(any(item.get("quote_id") == quote["id"] for item in recent))
        self.assertEqual(self.call("/quotes/" + quote["id"], token=stranger)[0], 404)

    def test_assistant_markdown_edit_is_reviewed_and_revision_checked(self):
        owner, _ = self.account("assistant-markdown-owner")
        stranger, _ = self.account("assistant-markdown-stranger")
        client = self.call('/clients', 'POST', {'name': 'Документ'}, owner)[1]['item']
        original = '# Проект\nСрок 30 дней.\n'
        file = self.call('/files', 'POST', {
            'client_id': client['id'], 'name': 'project.md',
            'content': base64.b64encode(original.encode()).decode(),
        }, owner)[1]['file']
        path = '/files/' + file['id']

        def tool(name, arguments):
            return {'content': None, 'tool_calls': [{
                'id': 'markdown-tool', 'type': 'function',
                'function': {'name': name, 'arguments': json.dumps(arguments)},
            }]}

        responses = [
            tool('read_markdown', {'id': file['id']}),
            tool('replace_markdown_text', {
                'id': file['id'], 'old_text': 'Срок 30 дней.',
                'new_text': 'Срок выполнения — 30 календарных дней.',
            }),
        ]
        with patch.dict(os.environ, OPENROUTER_API_KEY='test-not-real'), patch(
            'backend.assistant.query_model', side_effect=responses
        ) as model:
            status, result = self.call('/assistant/chat', 'POST', {
                'text': 'Сделай формулировку срока официальнее',
                'context': {'entity': 'files', 'id': file['id']},
            }, owner)
        self.assertEqual(status, 200, result)
        self.assertIn('Срок 30 дней.', model.call_args.args[0][-1]['content'])
        action = result['actions'][0]
        self.assertEqual(action['tool'], 'replace_markdown_text')
        self.assertEqual(self.call(path, token=owner, raw=True)[1], original.encode())
        self.assertEqual(self.call('/assistant/confirm', 'POST', {'id': action['id']}, stranger)[0], 404)
        applied = self.call('/assistant/confirm', 'POST', {'id': action['id']}, owner)
        self.assertEqual(applied[0], 200, applied)
        self.assertEqual(self.call('/assistant/confirm', 'POST', {'id': action['id']}, owner), applied)
        self.assertIn('30 календарных дней.', self.call(path, token=owner, raw=True)[1].decode())
        self.assertEqual(len(self.call(path + '/versions', token=owner)[1]['items']), 1)

        with patch.dict(os.environ, OPENROUTER_API_KEY='test-not-real'), patch(
            'backend.assistant.query_model', return_value=tool('replace_markdown_text', {
                'id': file['id'], 'old_text': 'Срок выполнения — 30 календарных дней.',
                'new_text': 'Срок выполнения — 31 календарный день.',
            })
        ):
            newer = self.call('/assistant/chat', 'POST', {'text': 'Измени срок',
                'context': {'entity': 'files', 'id': file['id']}}, owner)
        self.assertEqual(newer[0], 200, newer)
        current = applied[1]['result']['file']['sha256']
        self.assertEqual(self.call(path, 'PATCH', {
            'sha256': current,
            'content': base64.b64encode(b'# Another revision').decode(),
        }, owner)[0], 200)
        self.assertEqual(self.call('/assistant/confirm', 'POST', {
            'id': newer[1]['actions'][0]['id'],
        }, owner)[0], 409)

    def test_assistant_free_only_configuration(self):
        from backend.assistant import query_model
        from backend.business import DomainError

        with (
            patch.dict(os.environ, OPENROUTER_MODEL="paid-model"),
            self.assertRaises(DomainError),
        ):
            query_model([])

    def test_assistant_free_monthly_tokens_are_metered_and_exhausted(self):
        token, user_id = self.account("assistant-free-quota")
        from backend import ai_tokens

        usage = {"prompt_tokens": 9000, "completion_tokens": 1000, "total_tokens": 10000}
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
            patch("backend.assistant.query_model", return_value={"content": "Готово.", "_usage": usage}),
        ):
            quota = self.call("/assistant", token=token)[1]["quota"]
            self.assertEqual((quota["unit"], quota["remaining"]), ("tokens", ai_tokens.MONTHLY_TOKENS["starter"]))
            status, result = self.call("/assistant/chat", "POST", {"text": "Привет"}, token)
            self.assertEqual(status, 200)
            self.assertEqual(result["tokens_used"], 10000)
            self.assertEqual(result["quota"]["used"], 10000)
            # Leave less than a request needs: the next message is refused, nothing more is charged.
            with contextlib.closing(sqlite3.connect(self.mod.DB_PATH)) as con:
                con.execute("UPDATE rate_limits SET count=? WHERE key=?",
                            (ai_tokens.MONTHLY_TOKENS["starter"] - 100, ai_tokens.month_key(user_id)))
                con.commit()
            self.assertEqual(self.call("/assistant/chat", "POST", {"text": "Ещё"}, token)[0], 429)
            self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["remaining"], 100)

    def test_failed_provider_call_costs_no_tokens(self):
        token, _ = self.account("assistant-provider-failure")
        from backend.business import DomainError

        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
            patch("backend.assistant.query_model", side_effect=DomainError(502, "Модель недоступна")),
        ):
            self.assertEqual(self.call("/assistant/chat", "POST", {"text": "Привет"}, token)[0], 502)
            self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["used"], 0)

    def test_pro_allowance_then_wallet_tokens(self):
        token, user_id = self.account("assistant-pro-quota")
        from backend import ai_tokens

        with contextlib.closing(sqlite3.connect(self.mod.DB_PATH)) as con:
            con.execute("UPDATE users SET plan='pro',entitlement_until=? WHERE id=?", (int(time.time())+86400,user_id))
            con.commit()
        usage = {"prompt_tokens": 4000, "completion_tokens": 1000, "total_tokens": 5000}
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
            patch("backend.assistant.query_model", return_value={"content": "Готово.", "_usage": usage}),
        ):
            quota = self.call("/assistant", token=token)[1]["quota"]
            self.assertEqual(quota["monthly_limit"], ai_tokens.MONTHLY_TOKENS["pro_solo"])
            with contextlib.closing(sqlite3.connect(self.mod.DB_PATH)) as con:
                con.execute("INSERT INTO rate_limits(key,count,started) VALUES(?,?,?)",
                            (ai_tokens.month_key(user_id), ai_tokens.MONTHLY_TOKENS["pro_solo"] - 2000, int(time.time())))
                con.execute("INSERT INTO ai_token_wallets(user_id,balance,updated_at) VALUES(?,?,?)", (user_id, 10000, int(time.time())))
                con.commit()
            status, result = self.call("/assistant/chat", "POST", {"text": "Последний"}, token)
            self.assertEqual(status, 200)
            # 2 000 from the month, 3 000 from the wallet.
            self.assertEqual((result["quota"]["monthly_remaining"], result["quota"]["wallet"]), (0, 7000))
            with contextlib.closing(sqlite3.connect(self.mod.DB_PATH)) as con:
                reasons = [row[0] for row in con.execute("SELECT bucket FROM ai_token_ledger WHERE user_id=? ORDER BY bucket", (user_id,))]
            self.assertEqual(reasons, ["monthly", "wallet"])

    def test_stream_sends_deltas_and_final_message(self):
        token, _ = self.account("assistant-stream")

        def fake_stream(messages, on_delta):
            on_delta("**Привет")
            on_delta("!**")
            return {"content":"**Привет!**", "tool_calls":[]}

        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
            patch("backend.assistant.query_model_stream", side_effect=fake_stream),
        ):
            code, raw=self.call("/assistant/stream","POST",{"text":"Поздоровайся"},token,raw=True)
        self.assertEqual(code,200)
        text=raw.decode()
        self.assertIn('event: delta\ndata: {"text":"**Привет"}',text)
        self.assertIn('event: delta\ndata: {"text":"!**"}',text)
        self.assertIn('event: done',text)
        self.assertEqual(self.call("/assistant",token=token)[1]["messages"][-1]["content"],"**Привет!**")

    def test_free_image_assistant_can_prepare_quote_changes(self):
        """The free vision route must not silently lose quote-editing tools."""
        from types import SimpleNamespace
        from backend.assistant import assistant_model, query_model

        service = SimpleNamespace(wid=None, user={"plan": "free", "entitlement_until": 0})

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return b'{"choices":[{"message":{"content":"OK","tool_calls":[]}}]}'

        with (
            patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture-key",
                                    "OPENROUTER_FREE_VISION_MODEL": "qwen/qwen3.8-27b:free"}),
            patch("backend.assistant.urllib.request.urlopen", return_value=FakeResponse()) as opener,
        ):
            model, paid = assistant_model(service, has_image=True)
            self.assertEqual(model, "qwen/qwen3.8-27b:free")
            self.assertFalse(paid)
            result = query_model(
                [{"role": "user", "content": [{"type": "text", "text": "Составь смету"},
                                            {"type": "image_url", "image_url": {"url": "data:image/png;base64,YQ=="}}]}],
                model,
            )
        self.assertEqual(result["content"], "OK")
        sent = json.loads(opener.call_args.args[0].data)
        self.assertEqual(sent["model"], "qwen/qwen3.8-27b:free")
        self.assertIn("tools", sent)
        self.assertTrue(any(tool.get("function", {}).get("name") == "design_quote_layout"
                            for tool in sent["tools"]))
        self.assertFalse(any(tool.get("type") == "openrouter:web_search" for tool in sent["tools"]))

    def test_provider_stream_reassembles_fragmented_tool_calls(self):
        from backend.assistant import query_model_stream

        chunks=[
            {"choices":[{"delta":{"content":"Проверяю ","tool_calls":[{"index":0,"id":"tool-1","function":{"name":"list_","arguments":"{\"entity\":\""}}]}}]},
            {"choices":[{"delta":{"content":"сметы","tool_calls":[{"index":0,"function":{"name":"records","arguments":"quotes\"}"}}]}}]},
        ]
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def __iter__(self):
                yield from [("data: "+json.dumps(chunk)+"\n").encode() for chunk in chunks]
                yield b"data: [DONE]\n"
        deltas=[]
        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"), patch("backend.assistant.urllib.request.urlopen", return_value=FakeResponse()) as opener:
            result=query_model_stream([{"role":"user","content":"Сметы"}],deltas.append)
        self.assertEqual(deltas,["Проверяю ","сметы"])
        self.assertEqual(result["tool_calls"][0]["function"],{"name":"list_records","arguments":"{\"entity\":\"quotes\"}"})
        self.assertTrue(json.loads(opener.call_args.args[0].data)["stream"])


if __name__ == "__main__":
    unittest.main()
