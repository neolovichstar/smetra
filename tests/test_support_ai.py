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

    def test_provider_failure_hands_off_to_a_person(self):
        error = urllib.error.URLError("down")
        with patch("backend.model_transport.urllib.request.urlopen", side_effect=error):
            result = community._support_ai_reply({"id": "u"}, {}, [], "Не работает вход")
        self.assertTrue(result["escalate"])
        self.assertEqual(result["reason"], "support_ai_error")

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
