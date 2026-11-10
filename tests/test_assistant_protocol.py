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
            return self.tool("read-" + str(len(choices))) if len(choices) <= 4 else {"content": "Проверка завершена."}

        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch("backend.assistant.query_model", side_effect=provider):
            code, result = self.call("/assistant/chat", "POST", {"text": "Проверь связанные записи"}, token)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["answer"], "Проверка завершена.")
        self.assertEqual(choices, ["auto", "auto", "auto", "auto", "none"])
        self.assertEqual(assistant._MODEL_TOOL_CHOICE.get(), "auto")

    def test_textual_cloud_read_is_executed_as_a_tool_not_printed(self):
        token, _ = self.account("protocol-text-cloud")
        opaque = "live." + "a" * 120
        raw = (
            "<tool_call> <function=read_cloud_file> "
            f"<parameter=id>{opaque}</parameter> "
            "<parameter=page_start>37</parameter> "
            "</function> </tool_call>"
        )
        responses = [
            {"content": raw},
            {"content": "Прочитана страница 37. Данные проверены только на этой странице."},
        ]
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch(
            "backend.assistant.query_model", side_effect=responses
        ), patch("backend.assistant_app_tools.read", return_value={
            "name": "План.pdf", "excerpts": [{"page": 37, "text": "Площадь 20 м2"}],
            "truncated": True,
        }) as reader:
            code, result = self.call(
                "/assistant/chat", "POST", {"text": "Прочитай страницу 37 PDF"}, token
            )
        self.assertEqual(code, 200, result)
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(reader.call_args.args[1], "read_cloud_file")
        self.assertEqual(reader.call_args.args[2]["page_start"], 37)
        self.assertNotIn(opaque, result["answer"])
        self.assertNotIn("<tool_call>", result["answer"])
        self.assertIn("страница 37", result["answer"])

    def test_final_provider_tool_markup_never_exposes_cloud_reference(self):
        from backend import assistant

        opaque = "live." + "a" * 128
        xml = (f"<tool_call><function=read_cloud_file>"
               f"<parameter=id>{opaque}</parameter>"
               "<parameter=page_start>37</parameter></function></tool_call>")
        token = assistant._MODEL_TOOL_CHOICE.set("none")
        try:
            result = assistant._validated_reply({"content": xml})
        finally:
            assistant._MODEL_TOOL_CHOICE.reset(token)
        self.assertEqual(result["tool_calls"], [])
        self.assertNotIn(opaque, result["content"])
        self.assertNotIn("<tool_call>", result["content"])

    def test_textual_provider_markup_never_executes_write_tool(self):
        from backend import assistant

        raw = ("<tool_call><function=delete_quote>"
               "<parameter=id>some-id</parameter></function></tool_call>")
        result = assistant._validated_reply({"content": raw})
        self.assertEqual(result["tool_calls"], [])
        self.assertNotIn("<function=", result["content"])

    def test_leaked_live_reference_redacted_in_prose(self):
        from backend import assistant

        opaque = "live." + "b" * 95 + "=="
        result = assistant._validated_reply({"content": "Ссылка: " + opaque})
        self.assertEqual(result["tool_calls"], [])
        self.assertNotIn(opaque, result["content"])
        self.assertIn("скрыта", result["content"])

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

    def test_textual_cloud_tool_call_is_executed_as_structured_read(self):
        from backend.assistant import _validated_reply
        import json

        ref = "live.g" + "A" * 240
        message = (
            " <tool_call> <function=read_cloud_file> "
            "<parameter=id>" + ref + "</parameter> "
            "<parameter=page_start>37</parameter> </function> </tool_call>"
        )
        parsed = _validated_reply({"content": message})
        self.assertEqual(parsed["content"], "")
        self.assertEqual(len(parsed["tool_calls"]), 1)
        tool = parsed["tool_calls"][0]["function"]
        self.assertEqual(tool["name"], "read_cloud_file")
        self.assertEqual(json.loads(tool["arguments"]), {"id": ref, "page_start": 37})

    def test_textual_tool_call_rejects_writes_malformed_and_overlong_args(self):
        from backend.assistant import _validated_reply

        for value in (
            "<tool_call><function=create_quotes><parameter=title>X</parameter></function></tool_call>",
            "<tool_call><function=read_cloud_file><parameter=id>live." + "A" * 3000 + "</parameter></function></tool_call>",
            "<tool_call><function=read_cloud_file><parameter=id>fileA</parameter><parameter=page_start>0</parameter></function></tool_call>",
            "<tool_call><function=read_cloud_file><parameter=id>fileA</parameter><parameter=page_start>301</parameter></function></tool_call>",
            "Ответ: <tool_call><function=read_cloud_file><parameter=id>fileA</parameter></function></tool_call>",
        ):
            with self.subTest(value=value[:45]):
                parsed = _validated_reply({"content": value})
                self.assertEqual(parsed["tool_calls"], [])
                self.assertNotIn("<tool_call>", parsed["content"])
                self.assertNotIn("live.", parsed["content"])
                self.assertIn("Не удалось завершить чтение", parsed["content"])

    def test_cloud_reference_is_redacted_in_final_text(self):
        from backend.assistant import _validated_reply

        ref = "live.g" + "A" * 180
        parsed = _validated_reply({"content": "Файл: " + ref + ". Обработка продолжается."})
        self.assertNotIn(ref, parsed["content"])
        self.assertIn("[временная ссылка на файл скрыта]", parsed["content"])


    def test_budget_expiry_does_not_open_another_provider_request(self):
        from backend import assistant

        token = assistant._MODEL_DEADLINE.set(0)
        try:
            with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch("backend.assistant.urllib.request.urlopen", side_effect=AssertionError("provider called")), self.assertRaises(DomainError) as raised:
                assistant.query_model_stream([], lambda text: None)
            self.assertEqual(raised.exception.status, 504)
        finally:
            assistant._MODEL_DEADLINE.reset(token)
