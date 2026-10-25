"""A flaky free model never ends the chat before the user sees an answer."""
import json
import os
import unittest
from unittest.mock import patch

from backend.business import DomainError
from tests import test_business


def stream(*chunks, done=True):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            for chunk in chunks:
                yield ("data: " + json.dumps(chunk) + "\n").encode()
            if done:
                yield b"data: [DONE]\n"
    return FakeResponse()


class StreamFallbackTests(unittest.TestCase):
    def run_stream(self, responses, model="some/vendor:free"):
        from backend.assistant import query_model_stream

        sent, deltas = [], []

        def opener(request, timeout):
            sent.append(json.loads(request.data))
            return responses.pop(0)

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-not-real", "OPENROUTER_MODEL": model}), \
                patch("backend.assistant.urllib.request.urlopen", side_effect=opener):
            result = query_model_stream([{"role": "user", "content": "Привет"}], deltas.append)
        return result, sent, deltas

    def test_closed_stream_falls_back_to_free_router(self):
        result, sent, deltas = self.run_stream([
            stream(done=False),
            stream({"choices": [{"delta": {"content": "Здравствуйте"}}]}),
        ])
        self.assertEqual(result["content"], "Здравствуйте")
        self.assertEqual(deltas, ["Здравствуйте"])
        self.assertEqual([body["model"] for body in sent], ["some/vendor:free", "openrouter/free"])
        self.assertNotIn("reasoning", sent[1])

    def test_last_resort_answers_without_tools(self):
        result, sent, _ = self.run_stream([
            stream({"error": {"message": "upstream"}}),
            stream({"error": {"message": "upstream"}}),
            stream({"choices": [{"delta": {"content": "Ответ"}}]}),
        ])
        self.assertEqual(result["content"], "Ответ")
        self.assertIn("tools", sent[1])
        self.assertNotIn("tools", sent[2])

    def test_done_without_content_falls_back_instead_of_succeeding(self):
        result, sent, deltas = self.run_stream([
            stream(),
            stream({"choices": [{"delta": {"content": "Готовый ответ"}}]}),
        ])
        self.assertEqual(result["content"], "Готовый ответ")
        self.assertEqual(deltas, ["Готовый ответ"])
        self.assertEqual(sent[1]["model"], "openrouter/free")

    def test_provider_error_inside_http_200_is_not_treated_as_success(self):
        result, sent, deltas = self.run_stream([
            stream({"choices": [{"delta": {}, "finish_reason": "error"}]}),
            stream({"choices": [{"delta": {"content": "Проверил данные"}}]}),
        ])
        self.assertEqual(result["content"], "Проверил данные")
        self.assertEqual(deltas, ["Проверил данные"])
        self.assertEqual(len(sent), 2)

    def test_free_router_retries_without_reasoning_but_keeps_tools(self):
        result, sent, deltas = self.run_stream([
            stream({"error": {"message": "No capable provider"}}),
            stream({"choices": [{"delta": {"content": "Ответ"}}]}),
        ], model="openrouter/free")
        self.assertEqual(result["content"], "Ответ")
        self.assertEqual(deltas, ["Ответ"])
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[1]["model"], "openrouter/free")
        self.assertNotIn("reasoning", sent[1])
        self.assertIn("tools", sent[1])

    def test_partial_answer_is_not_replayed(self):
        from backend.assistant import query_model_stream

        calls = []

        def opener(request, timeout):
            calls.append(request)
            return stream({"choices": [{"delta": {"content": "Нача"}}]}, done=False)

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-not-real"}), \
                patch("backend.assistant.urllib.request.urlopen", side_effect=opener), \
                self.assertRaises(DomainError) as raised:
            query_model_stream([{"role": "user", "content": "Привет"}], lambda _: None)
        self.assertEqual(len(calls), 1)
        self.assertIn("прервался", str(raised.exception))


class ChatStreamTransactionTests(unittest.TestCase):
    """An SSE HTTP 200 is not a license to commit failed database work."""

    def handler(self):
        from io import BytesIO
        from types import SimpleNamespace

        return SimpleNamespace(
            wfile=BytesIO(), request_id="fixture-request",
            send_response=lambda _: None,
            send_header=lambda *_: None,
            end_headers=lambda: None,
        )

    def test_stream_error_rolls_back_runtime_transaction(self):
        from types import SimpleNamespace
        from backend.assistant import ChatStream

        commits = []
        service = SimpleNamespace(
            runtime_connection=SimpleNamespace(finish=commits.append),
        )
        handler = self.handler()
        with patch("backend.assistant.public_quota", return_value={"remaining": 100}), \\
                patch("backend.assistant.answer_chat", side_effect=DomainError(502, "Ошибка модели")):
            ChatStream(service, "Проверка", {}).write(handler)
        self.assertEqual(commits, [False])
        self.assertIn(b"event: error", handler.wfile.getvalue())

    def test_stream_success_commits_runtime_transaction(self):
        from types import SimpleNamespace
        from backend.assistant import ChatStream

        commits = []
        service = SimpleNamespace(
            runtime_connection=SimpleNamespace(finish=commits.append),
        )
        handler = self.handler()
        with patch("backend.assistant.public_quota", return_value={"remaining": 100}), \\
                patch("backend.assistant.answer_chat", return_value={"answer": "Готово"}):
            ChatStream(service, "Проверка", {}).write(handler)
        self.assertEqual(commits, [True])
        self.assertIn(b"event: done", handler.wfile.getvalue())


class DialogHistoryTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_new_dialog_reuses_an_untouched_one_and_takes_first_question_as_title(self):
        owner, _ = self.account("thread-reuse")
        first = self.call("/assistant/conversations", "POST", {"title": "Новый диалог"}, owner)
        self.assertEqual(first[0], 201, first[1])
        again = self.call("/assistant/conversations", "POST", {"title": "Новый диалог"}, owner)
        self.assertEqual(again[0], 200, again[1])
        self.assertEqual(again[1]["conversation"]["id"], first[1]["conversation"]["id"])
        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"), patch(
            "backend.assistant.query_model", return_value={"content": "Готово"},
        ):
            status, result = self.call("/assistant/chat", "POST", {
                "text": "Посчитай покраску стен в спальне",
                "conversation_id": first[1]["conversation"]["id"],
            }, owner)
        self.assertEqual(status, 200, result)
        items = self.call("/assistant/conversations", token=owner)[1]["items"]
        self.assertEqual([item["title"] for item in items], ["Посчитай покраску стен в спальне"])
        third = self.call("/assistant/conversations", "POST", {"title": "Новый диалог"}, owner)
        self.assertEqual(third[0], 201)
        self.assertNotEqual(third[1]["conversation"]["id"], first[1]["conversation"]["id"])


if __name__ == "__main__":
    unittest.main()
