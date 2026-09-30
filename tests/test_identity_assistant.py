import http.client
import json
import os
import concurrent.futures
import contextlib
import base64
import hashlib
import sqlite3
import time
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
            self.assertEqual(self.call("/assistant", token=stranger)[1]["quota"]["remaining"], 3)
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
            service = SimpleNamespace(con=con, wid=wid["id"])
            self.assertEqual(list_files(service, "brief"), {"files": []})
            owner_wid = con.execute("SELECT id FROM workspaces WHERE owner_id=?", (owner_id,)).fetchone()
            service.wid = owner_wid["id"]
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
        self.assertEqual(self.call("/assistant", token=owner)[1]["messages"], [])
        self.assertEqual(self.call("/assistant/conversations/" + conversation_id, "PATCH",
                                   {"title": "Важные заказы", "pinned": 1}, owner)[0], 200)
        self.assertEqual(self.call("/assistant/conversations/" + conversation_id, "DELETE", token=owner)[0], 200)
        self.assertEqual(self.call("/assistant/conversations/" + conversation_id, token=owner)[0], 404)

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
                [p["id"] for p in data["providers"]], ["yandex", "vk", "mail", "ok"]
            )
            self.assertNotIn("never-expose", json.dumps(data))

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

    def test_assistant_free_monthly_quota_is_atomic(self):
        token, _ = self.account("assistant-free-quota")
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
            patch("backend.assistant.query_model", return_value={"content": "Готово."}),
        ):
            self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["remaining"], 3)
            for _ in range(2):
                self.assertEqual(self.call("/assistant/chat", "POST", {"text": "Привет"}, token)[0], 200)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.call("/assistant/chat", "POST", {"text": "Ещё"}, token)[0], range(2)))
            self.assertEqual(sorted(results), [200, 429])
            self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["remaining"], 0)

    def test_failed_provider_call_refunds_quota(self):
        token, _ = self.account("assistant-provider-failure")
        from backend.business import DomainError

        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
            patch("backend.assistant.query_model", side_effect=DomainError(502, "Модель недоступна")),
        ):
            self.assertEqual(self.call("/assistant/chat", "POST", {"text": "Привет"}, token)[0], 502)
            self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["remaining"], 3)

    def test_pro_has_separate_bounded_monthly_allowance(self):
        token, user_id = self.account("assistant-pro-quota")
        with contextlib.closing(sqlite3.connect(self.mod.DB_PATH)) as con:
            con.execute("UPDATE users SET plan='pro',entitlement_until=? WHERE id=?", (int(time.time())+86400,user_id))
            con.commit()
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"),
            patch("backend.assistant.query_model", return_value={"content": "Готово."}),
        ):
            quota=self.call("/assistant", token=token)[1]["quota"]
            self.assertEqual((quota["limit"],quota["remaining"]),(100,100))
            key=hashlib.sha256(f"assistant:month:{quota['period']}:{user_id}".encode()).hexdigest()
            with contextlib.closing(sqlite3.connect(self.mod.DB_PATH)) as con:
                con.execute("INSERT INTO rate_limits(key,count,started) VALUES(?,?,?)",(key,99,int(time.time())))
                con.commit()
            self.assertEqual(self.call("/assistant/chat", "POST", {"text": "Последний"}, token)[0],200)
            self.assertEqual(self.call("/assistant/chat", "POST", {"text": "Ещё"}, token)[0],429)

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
