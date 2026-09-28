import io
import json
import os
import unittest
import urllib.request
import base64
import zipfile
from unittest.mock import patch

from tests.test_business import BusinessFlows
from backend.ai import capture_file
from backend.business import DomainError


class CaptureDraftTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp
    call = BusinessFlows.call
    account = BusinessFlows.account

    def test_openrouter_draft_is_review_only_and_keeps_unknown_prices_empty(self):
        token, _ = self.account("capture-owner")
        answer = {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                "title": "Лендинг для кофейни",
                "client": "",
                "description": "Дизайн и вёрстка",
                "terms": "Срок: три недели",
                "items": [{"name": "Дизайн", "description": "", "quantity": "1", "unit": "усл.", "unit_price": 0}],
            }, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 40},
        }
        requests = []

        original_urlopen = urllib.request.urlopen

        def reply(request, *args, **kwargs):
            if request.full_url.startswith("https://openrouter.ai/"):
                requests.append((request, kwargs.get("timeout")))
                return io.BytesIO(json.dumps(answer).encode())
            return original_urlopen(request, *args, **kwargs)

        with patch.dict(os.environ, OPENROUTER_API_KEY="test-key", OPENROUTER_MODEL="openrouter/free"):
            with patch("backend.ai.urllib.request.urlopen", side_effect=reply):
                status, result = self.call("/ai/draft", "POST", {"text": "Лендинг для кофейни, дизайн и вёрстка"}, token)
        self.assertEqual(status, 200, result)
        self.assertTrue(result["requires_review"])
        self.assertEqual(result["draft"]["items"][0]["unit_price"], 0)
        self.assertEqual(self.call("/quotes", token=token)[1]["quotes"], [])
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        sent = json.loads(request.data)
        self.assertEqual(sent["model"], "openrouter/free")
        self.assertEqual(sent["response_format"]["type"], "json_schema")
        self.assertEqual(timeout, 45)

    def test_file_type_pixels_and_archive_expansion_are_bounded(self):
        from PIL import Image

        picture = io.BytesIO()
        Image.new("RGB", (64, 64), "white").save(picture, format="PNG")
        text, image = capture_file({"name": "request.png", "mime": "image/png", "content": base64.b64encode(picture.getvalue()).decode()})
        self.assertEqual(text, "")
        self.assertTrue(image.startswith("data:image/jpeg;base64,"))
        with self.assertRaises(DomainError):
            capture_file({"name": "request.pdf", "mime": "image/png", "content": base64.b64encode(picture.getvalue()).decode()})
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            output.writestr("word/document.xml", "x" * 10_000_001)
        with self.assertRaises(DomainError):
            capture_file({"name": "request.docx", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "content": base64.b64encode(archive.getvalue()).decode()})


if __name__ == "__main__":
    unittest.main()
