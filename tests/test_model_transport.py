import io
import json
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from backend.model_transport import open_completion


class ModelFailoverTests(unittest.TestCase):
    def request(self, model="retired/model:free", stream=False):
        return urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
            json.dumps({"model": model, "stream": stream,
                        "messages": [{"role": "user", "content": "fixture"}],
                        "tools": [{"type": "function", "function": {"name": "read_quote"}}],
                        "reasoning": {"enabled": True}}).encode(),
            {"Authorization": "Bearer fixture-not-a-key"}, method="POST")

    def failure(self, code):
        return urllib.error.HTTPError("https://openrouter.ai", code, "fixture", {}, io.BytesIO())

    def test_retired_free_model_falls_back_with_tools_and_stream_intact(self):
        for stream in (False, True):
            with self.subTest(stream=stream), patch("urllib.request.urlopen",
                    side_effect=[self.failure(404), object()]) as opener:
                result = open_completion(self.request(stream=stream), 40)
                self.assertIsNotNone(result)
                sent = json.loads(opener.call_args.args[0].data)
                self.assertEqual(opener.call_count, 2)
                self.assertEqual(sent["model"], "openrouter/free")
                self.assertEqual(sent["stream"], stream)
                self.assertEqual(sent["tools"][0]["function"]["name"], "read_quote")
                self.assertNotIn("reasoning", sent)
                self.assertTrue(sent["provider"]["require_parameters"])

    def test_authentication_and_paid_model_errors_are_not_retried(self):
        for model, code in (("retired/model:free", 401), ("paid/model", 503),
                            ("openrouter/free", 429)):
            with self.subTest(model=model, code=code), patch("urllib.request.urlopen",
                    side_effect=self.failure(code)) as opener:
                with self.assertRaises(urllib.error.HTTPError):
                    open_completion(self.request(model), 40)
                self.assertEqual(opener.call_count, 1)

    def test_fallback_failure_is_bounded(self):
        with patch("urllib.request.urlopen",
                   side_effect=[self.failure(404), self.failure(503)]) as opener:
            with self.assertRaises(urllib.error.HTTPError):
                open_completion(self.request(), 40)
            self.assertEqual(opener.call_count, 2)

    def test_opened_stream_is_not_replayed_after_read_error(self):
        stream = io.BytesIO(b"partial")
        with patch("urllib.request.urlopen", return_value=stream) as opener:
            self.assertIs(open_completion(self.request(stream=True), 45), stream)
            self.assertEqual(opener.call_count, 1)
