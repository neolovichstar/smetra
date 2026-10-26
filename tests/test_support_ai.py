"""Support AI answers are parsed defensively and retried on the free router."""
import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from backend import community


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def reply(content):
    return FakeResponse(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


class SupportReplyParsingTests(unittest.TestCase):
    def test_accepts_strict_fenced_and_plain_answers(self):
        self.assertEqual(community._parse_support_reply('{"reply":"Да","escalate":false}')["reply"], "Да")
        fenced = '```json\n{"reply":"Откройте «Сметы»","escalate":false}\n```'
        self.assertEqual(community._parse_support_reply(fenced)["reply"], "Откройте «Сметы»")
        plain = community._parse_support_reply("Откройте раздел «Тариф и оплата».")
        self.assertEqual(plain, {"reply": "Откройте раздел «Тариф и оплата».", "escalate": False, "reason": ""})

    def test_rejects_empty_and_broken_json(self):
        for raw in ("", "   ", '{"reply": '):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                community._parse_support_reply(raw)

    def test_prompt_lists_server_prices_and_sections(self):
        prompt = community._support_prompt({"id": "u"}, {"account": {}})
        self.assertIn("790 ₽ в месяц", prompt)
        self.assertIn("«Калькуляторы»", prompt)
        self.assertIn("ИИ", prompt)


    def test_rejects_classifier_and_internal_reasoning_instead_of_showing_it(self):
        cases = (
            "User Safety: safe",
            "User Safety: safe\\nAnalysis: internal classification",
            "<think>internal analysis only</think>",
            "<think>unfinished internal analysis",
            {"reply": "User Safety: safe", "escalate": False},
            {"reply": ["not", "text"]},
            [],
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                community._parse_support_reply(raw)

    def test_extracts_final_answer_after_closed_thinking_block(self):
        for raw in (
            '<think>internal classification</think>{"reply":"Откройте «Сметы»","escalate":false}',
            '<analysis>internal classification</analysis>Откройте «Сметы».',
        ):
            with self.subTest(raw=raw):
                result = community._parse_support_reply(raw)
                self.assertIn("Откройте «Сметы»", result["reply"])
                self.assertNotIn("classification", result["reply"])

    def test_old_invalid_assistant_messages_are_masked_but_user_text_is_preserved(self):
        row = {"id": "fixture", "sender_id": None, "sender_type": "assistant",
               "body": "User Safety: safe", "metadata": "{}", "created_at": 0}
        self.assertEqual(community._message_view(row)["body"], community._SUPPORT_UNAVAILABLE_REPLY)
        row["sender_type"] = "user"
        self.assertEqual(community._message_view(row)["body"], "User Safety: safe")


class SupportReplyTransportTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "SUPPORT_AI_MODEL": "some/model:free"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_answers_without_escalation(self):
        with patch("backend.model_transport.urllib.request.urlopen", return_value=reply('{"reply":"Готово","escalate":false}')):
            result = community._support_ai_reply({"id": "u"}, {}, [], "Как создать смету?")
        self.assertEqual(result["reply"], "Готово")
        self.assertFalse(result["escalate"])

    def test_retries_once_without_json_mode_then_answers(self):
        calls = []

        def fake(request, timeout):
            body = json.loads(request.data)
            calls.append(body)
            if len(calls) == 1:
                return reply("")
            return reply("Нажмите «Отправить клиенту».")

        with patch("backend.model_transport.urllib.request.urlopen", side_effect=fake):
            result = community._support_ai_reply({"id": "u"}, {}, [], "Как отправить смету?")
        self.assertEqual(result["reply"], "Нажмите «Отправить клиенту».")
        self.assertFalse(result["escalate"])
        self.assertEqual(calls[1]["model"], "openrouter/free")
        self.assertNotIn("response_format", calls[1])

    def test_human_request_always_escalates(self):
        with patch("backend.model_transport.urllib.request.urlopen", return_value=reply('{"reply":"Передал","escalate":false}')):
            result = community._support_ai_reply({"id": "u"}, {}, [], "Позовите оператора, пожалуйста")
        self.assertTrue(result["escalate"])

    def test_explicit_human_request_never_calls_openrouter(self):
        with patch("backend.model_transport.urllib.request.urlopen",
                   side_effect=AssertionError("must not contact OpenRouter")):
            result = community._support_ai_reply(
                {"id": "u"}, {}, [], "Позовите живого оператора, пожалуйста"
            )
        self.assertTrue(result["escalate"])
        self.assertEqual(result["reason"], "user_requested_human")

    def test_nonboolean_escalation_does_not_summon_an_employee(self):
        with patch("backend.model_transport.urllib.request.urlopen",
                   return_value=reply('{"reply":"Откройте настройки","escalate":"false"}')):
            result = community._support_ai_reply({"id": "u"}, {}, [], "Где настройки?")
        self.assertFalse(result["escalate"])

    def test_provider_rate_limit_is_not_replayed(self):
        rate_limit = urllib.error.HTTPError(
            "https://openrouter.ai", 429, "rate limit", {}, io.BytesIO()
        )
        with patch("backend.model_transport.urllib.request.urlopen",
                   side_effect=rate_limit) as opener:
            result = community._support_ai_reply({"id": "u"}, {}, [], "Где сметы?")
        self.assertTrue(result["escalate"])
        self.assertEqual(result["reason"], "support_ai_error")
        self.assertEqual(opener.call_count, 1)

    def test_provider_failure_hands_off_to_a_person(self):
        error = urllib.error.URLError("down")
        with patch("backend.model_transport.urllib.request.urlopen", side_effect=error):
            result = community._support_ai_reply({"id": "u"}, {}, [], "Не работает вход")
        self.assertTrue(result["escalate"])
        self.assertEqual(result["reason"], "support_ai_error")


    def test_classifier_response_is_retried_and_only_final_answer_is_returned(self):
        with patch("backend.community.urllib.request.urlopen", side_effect=[
            reply("User Safety: safe"),
            reply('{"reply":"Опишите, что не получается с ассистентом.","escalate":false}'),
        ]) as opener:
            result = community._support_ai_reply({"id": "u"}, {}, [], "Ассистент и лимиты")
        self.assertEqual(opener.call_count, 2)
        self.assertNotIn("User Safety", result["reply"])
        self.assertFalse(result["escalate"])
        sent = json.loads(opener.call_args_list[0].args[0].data)
        self.assertTrue(sent["reasoning"]["exclude"])

    def test_repeated_classifier_response_hands_off_with_a_normal_message(self):
        with patch("backend.community.urllib.request.urlopen", side_effect=lambda *_args, **_kwargs: reply("User Safety: safe")):
            result = community._support_ai_reply({"id": "u"}, {}, [], "Ассистент и лимиты")
        self.assertTrue(result["escalate"])
        self.assertEqual(result["reason"], "support_ai_error")
        self.assertNotIn("User Safety", result["reply"])

    def test_malformed_provider_shape_is_bounded_and_does_not_crash_support(self):
        for shape in ([], {"choices": None}, {"choices": [None]}):
            with self.subTest(shape=shape), patch(
                "backend.community.urllib.request.urlopen",
                side_effect=lambda *_args, **_kwargs: FakeResponse(json.dumps(shape).encode()),
            ) as opener:
                result = community._support_ai_reply({"id": "u"}, {}, [], "Как создать смету?")
            self.assertTrue(result["escalate"])
            self.assertEqual(opener.call_count, 2)

    def test_history_skips_service_messages(self):
        captured = {}

        def fake(request, timeout):
            captured.update(json.loads(request.data))
            return reply('{"reply":"Ок","escalate":false}')

        history = [{"sender_type": "system", "body": "Обращение создано"},
                   {"sender_type": "user", "body": "Привет"},
                   {"sender_type": "admin", "body": "Проверим"}]
        with patch("backend.model_transport.urllib.request.urlopen", side_effect=fake):
            community._support_ai_reply({"id": "u"}, {}, history, "Спасибо")
        roles = [m["role"] for m in captured["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        self.assertTrue(captured["messages"][2]["content"].startswith("Сотрудник поддержки"))


if __name__ == "__main__":
    unittest.main()
