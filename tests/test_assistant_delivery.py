"""Durable foreground streaming uses the same queue as scheduler recovery."""
import base64
import io
import json
import time
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from backend.business import DomainError, Service
from backend.assistant_delivery import DurableChatStream
from tests import test_business


class AssistantDeliveryTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def setUp(self):
        test_business.BusinessFlows.setUp(self)
        environment = patch.dict(os.environ, ASSISTANT_WORKER_SECRET="isolated-worker-test-secret-0123456789", OPENROUTER_API_KEY="fixture-only")
        environment.start()
        self.addCleanup(environment.stop)

    def enqueue(self, token, **fields):
        code, result = self.call("/assistant/jobs", "POST", {"text": "Проверь данные", **fields}, token, key=uuid.uuid4().hex)
        self.assertEqual(code, 202, result)
        return result["job"]

    @staticmethod
    def provider(messages, on_delta):
        on_delta("Проверил ")
        on_delta("данные")
        return {"content": "Проверил данные"}

    def test_stream_completes_job_and_replay_never_runs_or_charges_twice(self):
        token, _ = self.account("durable-replay")
        job = self.enqueue(token)
        with patch("backend.assistant.query_model_stream", side_effect=self.provider) as model:
            code, stream = self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
            self.assertEqual(code, 200, stream)
            self.assertIn(b"event: delta", stream)
            self.assertIn(b"event: done", stream)
            completed = self.call("/assistant/jobs/" + job["id"], token=token)[1]["job"]
            self.assertEqual(completed["status"], "completed")
            used = self.call("/assistant", token=token)[1]["quota"]["used"]
            with patch("backend.assistant_jobs.claim", side_effect=AssertionError("completed replay acquired queue")):
                code, replay = self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
            self.assertEqual(code, 200)
            self.assertIn(b"event: done", replay)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["used"], used)
        self.assertEqual(len(self.call("/assistant", token=token)[1]["messages"]), 2)

    def test_disconnected_browser_does_not_cancel_saved_job(self):
        token, user_id = self.account("durable-disconnect")
        job = self.enqueue(token)

        class Disconnected(io.BytesIO):
            def write(self, value):
                if value.startswith(b"event: delta"):
                    raise BrokenPipeError("browser left")
                return super().write(value)

        handler = SimpleNamespace(wfile=Disconnected(), send_response=lambda *_: None,
                                  send_header=lambda *_: None, end_headers=lambda: None,
                                  request_id="delivery-fixture", headers={})
        with self.mod.db() as con:
            service = Service(handler, con, self.mod.ORIGIN)
            service.user = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            service.wid = con.execute("SELECT workspace_id FROM assistant_jobs WHERE id=?", (job["id"],)).fetchone()[0]
            with patch("backend.assistant.query_model_stream", side_effect=self.provider):
                DurableChatStream(service, job["id"]).write(handler)
        row = self.call("/assistant/jobs/" + job["id"], token=token)[1]["job"]
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["result"]["answer"], "Проверил данные")
        self.assertEqual(len(self.call("/assistant", token=token)[1]["messages"]), 2)

    def test_private_stream_cannot_drive_another_users_job(self):
        owner, _ = self.account("durable-owner")
        outsider, _ = self.account("durable-outsider")
        job = self.enqueue(owner)
        with patch("backend.assistant.query_model_stream", side_effect=AssertionError("provider called")):
            self.assertEqual(self.call("/assistant/stream", "POST", {"job_id": job["id"]}, outsider)[0], 404)
        self.assertEqual(self.call("/assistant/jobs/" + job["id"], token=owner)[1]["job"]["status"], "queued")

    def test_busy_user_waits_without_consuming_provider_attempts(self):
        token, _ = self.account("durable-busy")
        job = self.enqueue(token)
        for _ in range(4):
            with patch("backend.redis_infra.acquire_lock", return_value=None):
                code, stream = self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
            self.assertEqual(code, 200)
            self.assertIn(b"event: background", stream)
            with self.mod.db() as con:
                row = con.execute("SELECT * FROM assistant_jobs WHERE id=?", (job["id"],)).fetchone()
                self.assertEqual(row["status"], "retry")
                self.assertEqual(row["attempts"], 0)
                self.assertLessEqual(row["next_attempt_at"], int(time.time()) + 5)
                con.execute("UPDATE assistant_jobs SET next_attempt_at=0 WHERE id=?", (job["id"],))
        with patch("backend.assistant.query_model_stream", side_effect=self.provider):
            self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
        self.assertEqual(self.call("/assistant/jobs/" + job["id"], token=token)[1]["job"]["status"], "completed")

    def test_new_chat_does_not_reuse_an_empty_conversation_with_queued_work(self):
        token, _ = self.account("durable-new-chat")
        first = self.call("/assistant/conversations", "POST", {}, token)[1]["conversation"]
        self.enqueue(token, conversation_id=first["id"])
        second = self.call("/assistant/conversations", "POST", {}, token)[1]["conversation"]
        self.assertNotEqual(second["id"], first["id"])

    def test_proposals_keep_their_conversation_and_confirm_without_private_metadata(self):
        token, _ = self.account("durable-proposal-scope")
        thread = self.call("/assistant/conversations", "POST", {}, token)[1]["conversation"]
        job = self.enqueue(token, conversation_id=thread["id"])
        reply = {"content": None, "tool_calls": [{"id": "new-client", "type": "function", "function": {
            "name": "create_clients", "arguments": json.dumps({"name": "Клиент диалога"})}}]}
        with patch("backend.assistant.query_model_stream", return_value=reply):
            self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
        data = self.call("/assistant", token=token)[1]
        action = data["actions"][0]
        self.assertEqual(action["conversation_id"], thread["id"])
        self.assertNotIn("_conversation_id", action["arguments"])
        code, confirmed = self.call("/assistant/confirm", "POST", {"id": action["id"]}, token)
        self.assertEqual(code, 200, confirmed)
        self.assertEqual(len(self.call("/clients", token=token)[1]["items"]), 1)

    def test_provider_failure_keeps_retryable_job_in_background(self):
        token, _ = self.account("durable-retry")
        job = self.enqueue(token)
        with patch("backend.assistant.query_model_stream", side_effect=DomainError(502, "Модель занята")):
            code, stream = self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
        self.assertEqual(code, 200)
        self.assertIn(b"event: background", stream)
        self.assertNotIn(b"event: done", stream)
        self.assertEqual(self.call("/assistant/jobs/" + job["id"], token=token)[1]["job"]["status"], "retry")
        self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["used"], 0)

    def test_explicit_cancel_during_stream_leaves_no_history_or_actions(self):
        token, _ = self.account("durable-cancel")
        job = self.enqueue(token)

        def cancel(messages, on_delta):
            on_delta("Начало")
            self.assertEqual(self.call("/assistant/jobs/" + job["id"], "DELETE", token=token)[0], 200)
            return {"content": "Не сохранять"}

        with patch("backend.assistant.query_model_stream", side_effect=cancel):
            code, stream = self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
        self.assertEqual(code, 200)
        self.assertIn(b'"cancelled": true', stream)
        self.assertEqual(self.call("/assistant/jobs/" + job["id"], token=token)[1]["job"]["status"], "cancelled")
        result = self.call("/assistant", token=token)[1]
        self.assertEqual(result["messages"], [])
        self.assertEqual(result["actions"], [])
        self.assertEqual(result["quota"]["used"], 0)

    def test_owned_saved_photo_reaches_vision_and_foreign_photo_is_rejected(self):
        token, _ = self.account("durable-photo")
        outsider, _ = self.account("durable-photo-outsider")
        content = io.BytesIO()
        Image.new("RGB", (24, 24), "gray").save(content, "PNG")
        code, uploaded = self.call("/files", "POST", {"assistant_upload": True, "name": "photo.png", "content": base64.b64encode(content.getvalue()).decode()}, token, key=uuid.uuid4().hex)
        self.assertEqual(code, 201, uploaded)
        file_id = uploaded["file"]["id"]
        self.assertEqual(self.call("/assistant/jobs", "POST", {"file_ids": [file_id]}, outsider, key=uuid.uuid4().hex)[0], 404)
        job = self.enqueue(token, text="", file_ids=[file_id])

        def vision(messages, on_delta):
            image = next(part for part in messages[-1]["content"] if part["type"] == "image_url")
            self.assertTrue(image["image_url"]["url"].startswith("data:image/png;base64,"))
            return self.provider(messages, on_delta)

        with patch("backend.assistant.query_model_stream", side_effect=vision):
            code, stream = self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
        self.assertEqual(code, 200, stream)
        self.assertEqual(self.call("/assistant/jobs/" + job["id"], token=token)[1]["job"]["status"], "completed")

    def test_cancelled_or_claimed_jobs_are_not_started_again(self):
        token, _ = self.account("durable-claimed")
        job = self.enqueue(token)
        with self.mod.db() as con:
            con.execute("UPDATE assistant_jobs SET status='running',lease_until=?,lease_token='other' WHERE id=?", (self.mod.now() + 120, job["id"]))
        with patch("backend.assistant.query_model_stream", side_effect=AssertionError("duplicate provider")):
            code, stream = self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
        self.assertEqual(code, 200)
        self.assertIn(b"event: background", stream)
        with self.mod.db() as con:
            con.execute("UPDATE assistant_jobs SET status='cancelled' WHERE id=?", (job["id"],))
        with patch("backend.assistant.query_model_stream", side_effect=AssertionError("cancelled provider")):
            code, stream = self.call("/assistant/stream", "POST", {"job_id": job["id"]}, token, raw=True)
        self.assertEqual(code, 200)
        self.assertIn(b'"cancelled": true', stream)

