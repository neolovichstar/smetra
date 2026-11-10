"""Model protocol and bounded tool-loop regressions; no external provider calls."""
import os
import unittest
from unittest.mock import patch

from backend.business import DomainError
from tests import test_business
from tests.test_assistant_stream_fallback import stream


class AssistantProtocolTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    @staticmethod
    def tool(call_id):
        return {"content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": "overview", "arguments": "{}"}}]}

    def test_two_reads_are_followed_by_an_actual_answer(self):
        token, _ = self.account("protocol-chain")
        replies = [self.tool("read-1"), self.tool("read-2"), {"content": "Оба источника проверены."}]
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch("backend.assistant.query_model", side_effect=replies) as provider:
            code, result = self.call("/assistant/chat", "POST", {"text": "Сверь два источника и объясни результат"}, token)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["answer"], "Оба источника проверены.")
        self.assertEqual(provider.call_count, 3)

    def test_final_round_disables_more_tools_and_uses_collected_results(self):
        from backend import assistant

        token, _ = self.account("protocol-final")
        choices = []

        def provider(messages):
            choices.append(assistant._MODEL_TOOL_CHOICE.get())
            return self.tool("read-" + str(len(choices))) if len(choices) <= 3 else {"content": "Проверка завершена."}

        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch("backend.assistant.query_model", side_effect=provider):
            code, result = self.call("/assistant/chat", "POST", {"text": "Проверь связанные записи"}, token)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["answer"], "Проверка завершена.")
        self.assertEqual(choices, ["auto", "auto", "auto", "none"])
        self.assertEqual(assistant._MODEL_TOOL_CHOICE.get(), "auto")

    def test_textual_cloud_read_is_dispatched_and_not_exposed_in_chat(self):
        import json

        token, _ = self.account("protocol-textual-cloud")
        secret_ref = "live.g" + "A" * 220
        markup = ("<tool_call><function=read_cloud_file>"
                  "<parameter=id>" + secret_ref + "</parameter>"
                  "<parameter=page_start>37</parameter>"
                  "</function></tool_call>")
        seen = []

        def model(messages):
            seen.append(messages)
            return {"content": markup} if len(seen) == 1 else {
                "content": "Страница 37 проверена, указан размер 19 м²."
            }

        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch(
            "backend.assistant.query_model", side_effect=model
        ), patch(
            "backend.assistant_app_tools.read",
            return_value={"excerpts": [{"page": 37, "text": "Комната 19 м²"}]},
        ) as read_tool:
            status, result = self.call("/assistant/chat", "POST", {
                "text": "Изучи страницу 37 проекта в облаке"
            }, token)
        self.assertEqual(status, 200, result)
        self.assertEqual(read_tool.call_count, 1)
        self.assertEqual(read_tool.call_args.args[1], "read_cloud_file")
        self.assertEqual(read_tool.call_args.args[2], {"id": secret_ref, "page_start": 37})
        self.assertNotIn(secret_ref, result["answer"])
        self.assertIn("Страница 37", result["answer"])
        self.assertEqual(len(seen), 2)

    def test_textual_tool_markup_never_executes_write_actions(self):
        from backend.assistant import _validated_reply

        for function in ("create_quotes", "delete_files", "update_profiles"):
            markup = (f"<tool_call><function={function}>"
                      "<parameter=id>123</parameter></function></tool_call>")
            parsed = _validated_reply({"content": markup})
            self.assertEqual(parsed["tool_calls"], [])
            self.assertNotIn("<tool_call>", parsed["content"])
            self.assertIn("Не удалось завершить", parsed["content"])

    def test_streamed_cloud_tool_markup_is_never_visible_to_client(self):
        token, _ = self.account("protocol-stream-xml")
        secret_ref = "live.g" + "B" * 220
        markup = ("<tool_call><function=read_cloud_file>"
                  "<parameter=id>" + secret_ref + "</parameter>"
                  "</function></tool_call>")
        rounds = []

        def provider(messages, on_delta, **_kwargs):
            rounds.append(messages)
            if len(rounds) == 1:
                on_delta(markup[:30])
                on_delta(markup[30:])
                return {"content": markup}
            on_delta("Проверена ")
            on_delta("страница 1")
            return {"content": "Проверена страница 1"}

        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch(
            "backend.assistant.query_model_stream", side_effect=provider
        ), patch(
            "backend.assistant_app_tools.read",
            return_value={"excerpts": [{"page": 1, "text": "Окно 3 м"}]},
        ):
            status, raw = self.call("/assistant/stream", "POST", {
                "text": "Прочитай нужный файл в облаке"
            }, token, raw=True)
        self.assertEqual(status, 200, raw)
        text = raw.decode()
        self.assertNotIn(secret_ref, text)
        self.assertNotIn("<tool_call>", text)
        self.assertIn("event: done", text)
        self.assertIn("Проверена страница 1", text)

    def test_malformed_model_calls_fail_without_500_or_pending_changes(self):
        token, _ = self.account("protocol-malformed")
        invalid = [
            {"tool_calls": [{"function": {"name": "create_clients", "arguments": '{"name":"Не создавать"}'}}]},
            {"tool_calls": {"function": "wrong"}},
            {"tool_calls": [None]},
            {"content": {"bad": "shape"}},
            {"tool_calls": [{"id": "dup", "function": {"name": "overview", "arguments": "{}"}}, {"id": "dup", "function": {"name": "overview", "arguments": "{}"}}]},
        ]
        for response in invalid:
            with self.subTest(response=response), patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch("backend.assistant.query_model", return_value=response):
                code, result = self.call("/assistant/chat", "POST", {"text": "Проверь данные"}, token)
                self.assertEqual(code, 502, result)
                self.assertEqual(self.call("/assistant", token=token)[1]["actions"], [])
                self.assertEqual(self.call("/assistant", token=token)[1]["messages"], [])


class StreamingShapeTests(unittest.TestCase):
    def test_malformed_delta_falls_back_instead_of_attribute_error(self):
        from backend.assistant import query_model_stream

        replies = [stream({"choices": [{"delta": "invalid"}]}), stream({"choices": [{"delta": {"content": "Готовый ответ"}}]})]
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch("backend.assistant.urllib.request.urlopen", side_effect=lambda *args, **kwargs: replies.pop(0)):
            result = query_model_stream([], lambda text: None)
        self.assertEqual(result["content"], "Готовый ответ")

    def test_tool_fragments_assemble_and_validate_before_execution(self):
        from backend.assistant import query_model_stream

        response = stream(
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-", "function": {"name": "over", "arguments": "{"}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "1", "function": {"name": "view", "arguments": "}"}}]}}]},
        )
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch("backend.assistant.urllib.request.urlopen", return_value=response):
            result = query_model_stream([], lambda text: None)
        self.assertEqual(result["tool_calls"][0]["id"], "call-1")
        self.assertEqual(result["tool_calls"][0]["function"], {"name": "overview", "arguments": "{}"})

    def test_textual_markup_and_cloud_ids_are_safely_redacted(self):
        from backend.assistant import _validated_reply
        import json

        secret_ref = "live.g" + "C" * 200
        xml = (" <tool_call> <function=read_cloud_file> "
               "<parameter=id>" + secret_ref + "</parameter> "
               "<parameter=page_start>37</parameter> </function> </tool_call> ")
        value = _validated_reply({"content": xml})
        self.assertEqual(value["content"], "")
        self.assertEqual(len(value["tool_calls"]), 1)
        call = value["tool_calls"][0]["function"]
        self.assertEqual(call["name"], "read_cloud_file")
        self.assertEqual(json.loads(call["arguments"]), {"id": secret_ref, "page_start": 37})

        quoted = _validated_reply({"content": "Файл: " + secret_ref + " проверяю."})
        self.assertNotIn(secret_ref, quoted["content"])
        self.assertIn("[временная ссылка на файл скрыта]", quoted["content"])

        from backend import assistant
        token = assistant._MODEL_TOOL_CHOICE.set("none")
        try:
            cannot_execute = _validated_reply({"content": xml})
            self.assertEqual(cannot_execute["tool_calls"], [])
            self.assertNotIn(secret_ref, cannot_execute["content"])
        finally:
            assistant._MODEL_TOOL_CHOICE.reset(token)

    def test_budget_expiry_does_not_open_another_provider_request(self):
        from backend import assistant

        token = assistant._MODEL_DEADLINE.set(0)
        try:
            with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch("backend.assistant.urllib.request.urlopen", side_effect=AssertionError("provider called")), self.assertRaises(DomainError) as raised:
                assistant.query_model_stream([], lambda text: None)
            self.assertEqual(raised.exception.status, 504)
        finally:
            assistant._MODEL_DEADLINE.reset(token)
