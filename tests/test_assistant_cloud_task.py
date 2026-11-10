"""Current user request must outrank old chats; cloud file search cannot be optional."""
import os
import unittest
from unittest.mock import patch

from backend.assistant_cloud_task import request_info, prepare
from tests import test_business


class CurrentCloudRequestTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_exact_user_phrase_extracts_document_title_not_the_instruction(self):
        phrase = ("в гугл диске найди пдф файл че то про дом на набережной "
                  "и прочитай его полностью и из него сделай смету")
        self.assertEqual(request_info(phrase), {
            "query": "дом на набережной", "provider": "google_drive"
        })
        self.assertEqual(request_info("найди в Google Drive PDF «Дом на набережной.pdf»"),
                         {"query": "Дом на набережной.pdf", "provider": "google_drive"})
        self.assertIsNone(request_info("Составь смету по этим размерам: 3 на 4"))

    def test_search_and_read_are_server_calls_before_model_reply(self):
        phrase = ("в гугл диске найди пдф файл че то про дом на набережной "
                  "и прочитай его полностью и из него сделай смету")
        token, _ = self.account("grounded-cloud-request")
        calls, model_messages = [], []
        def reader(service, name, args):
            calls.append((name, args))
            if name == "list_cloud_files":
                return {"files": [
                    {"id": "live." + "q" * 120, "name": "Дом на набережной.pdf",
                     "mime": "application/pdf", "provider": "google_drive", "size": 10000},
                    {"id": "live.other", "name": "Квартира.pdf",
                     "mime": "application/pdf", "provider": "yandex_disk", "size": 1000},
                ], "errors": [], "truncated": False}
            if name == "read_cloud_file":
                return {"name": "Дом на набережной.pdf", "excerpts": [
                    {"page": 1, "text": "Площадь 120 м2; спецификация материалов"}],
                    "page_start": 1, "pages_scanned": 1,
                    "total_pages": 1, "truncated": False, "source_stored": False}
            raise AssertionError(name)
        def provider(messages):
            model_messages.append(messages)
            return {"content": "Изучил страницу 1 PDF. Подготовлю смету только по подтверждённым данным."}
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch(
            "backend.assistant_app_tools.read", side_effect=reader
        ), patch("backend.assistant.query_model", side_effect=provider), patch(
            "backend.assistant_recall.automatic_history_context",
            side_effect=AssertionError("Never replace a current PDF task with old chat recall"),
        ):
            status, result = self.call("/assistant/chat", "POST", {"text": phrase}, token)
        self.assertEqual(status, 200, result)
        self.assertEqual([name for name, _ in calls], ["list_cloud_files", "read_cloud_file"])
        self.assertEqual(calls[0][1]["query"], "дом на набережной")
        self.assertEqual(model_messages[0][-1]["role"], "tool")
        self.assertIn("Площадь 120 м2", model_messages[0][-1]["content"])
        self.assertEqual(model_messages[0][-2]["tool_calls"][0]["function"]["name"], "read_cloud_file")
        self.assertIn("Изучил", result["answer"])

    def test_does_not_select_ambiguous_pdf_or_other_provider(self):
        def fake(service, name, args):
            return {
                "files": [
                    {"id": "a", "name": "Дом на набережной.pdf", "mime": "application/pdf", "provider": "google_drive"},
                    {"id": "b", "name": "Дом на набережной.pdf", "mime": "application/pdf", "provider": "google_drive"},
                    {"id": "c", "name": "Дом на набережной.pdf", "mime": "application/pdf", "provider": "yandex_disk"},
                ], "errors": [], "truncated": False,
            }
        with patch("backend.assistant_app_tools.read", side_effect=fake) as reader:
            result = prepare(object(), "найди pdf «дом на набережной» в google drive")
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0][2]["files"]), 2)
        self.assertEqual(reader.call_count, 1)

    def test_wrong_empty_message_reply_is_retried_not_shown(self):
        token, _ = self.account("nonempty-not-empty")
        responses = iter([{"content": "Вы ничего не написали в этом сообщении."},
                          {"content": "Понял запрос. Проверяю данные."}])
        with patch.dict(os.environ, OPENROUTER_API_KEY="fixture-only"), patch(
            "backend.assistant.query_model", side_effect=lambda messages: next(responses)
        ) as provider:
            status, result = self.call("/assistant/chat", "POST", {"text": "Сделай смету по квартире"}, token)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["answer"], "Понял запрос. Проверяю данные.")
        self.assertEqual(provider.call_count, 2)
