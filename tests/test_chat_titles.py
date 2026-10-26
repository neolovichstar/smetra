"""Regression tests for short chat names and first-message ownership."""
import os
import unittest
from unittest.mock import patch

from backend.chat_titles import clean_title, fallback_title, generate_title, TITLE_LIMIT


class ChatTitleTests(unittest.TestCase):
    def test_first_message_title_fits_sidebar_without_cutting_words(self):
        title = fallback_title("Пожалуйста, сделай профессиональный расчёт косметического ремонта комнаты площадью 20 квадратных метров")
        self.assertLessEqual(len(title), TITLE_LIMIT)
        self.assertFalse(title.endswith((" ", ",", "-", ".")))
        self.assertNotEqual(title, "Новый диалог")

    def test_conversation_titles_strip_markup_and_secrets(self):
        title = clean_title("  <script>скрипт</script> Проверить sk-or-v1-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890  ")
        self.assertNotIn("sk-or-v1-", title)
        self.assertNotIn("<script>", title)
        self.assertLessEqual(len(title), TITLE_LIMIT)
        self.assertNotIn("test@example.com", clean_title("Смета test@example.com"))

    def test_short_first_message_avoids_extra_provider_call(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "testing-only"}, clear=False):
            with patch("backend.assistant.open_completion") as completion:
                title = generate_title("Подготовь смету на кухню", "openrouter/free")
        self.assertIn("смету", title.lower())
        completion.assert_not_called()

    def test_long_request_uses_model_generated_semantic_name(self):
        import json
        from io import BytesIO

        class Response:
            def __enter__(self):
                return BytesIO(json.dumps({"choices": [{"message": {"content": "Смета косметического ремонта"}}]}).encode())
            def __exit__(self, *args):
                pass

        request = "Нужно составить список работ для косметического ремонта гостиной с покраской потолков и монтажом плинтусов"
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "testing-only"}, clear=False):
            with patch("backend.assistant.open_completion", return_value=Response()) as completion:
                title = generate_title(request, "openrouter/free")
        self.assertEqual(title, "Смета косметического ремонта")
        completion.assert_called_once()
