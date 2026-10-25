"""Security and resilience regressions for the assistant tool boundary."""

import json
import os
import unittest
from unittest.mock import patch

from backend.assistant import normalize_tool_calls, tool_result_message
from backend.business import DomainError
from tests import test_business
from tests.test_assistant_jobs import SECRET, worker_token


class AssistantSecurityRegressions(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_partial_stream_error_refunds_unsaved_answer(self):
        owner, _ = self.account("stream-refund")
        def fail_after_delta(_messages, on_delta):
            on_delta("Частичный ответ")
            raise DomainError(502, "Ошибка провайдера")

        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"), patch(
            "backend.assistant.query_model_stream", side_effect=fail_after_delta,
        ):
            status, raw = self.call("/assistant/stream", "POST", {"text": "Проверь"}, owner, raw=True)
        self.assertEqual(status, 200)
        output = raw.decode()
        self.assertIn("event: delta", output)
        self.assertIn("event: error", output)
        self.assertNotIn("event: done", output)
        self.assertEqual(self.call("/assistant", token=owner)[1]["quota"]["used"], 0)
        self.assertEqual(self.call("/assistant", token=owner)[1]["messages"], [])

    def test_malformed_tool_envelopes_rejected_without_side_effects(self):
        valid = {"id": "call-1", "type": "function", "function": {
            "name": "list_records", "arguments": '{"entity":"clients"}',
        }}
        self.assertEqual(normalize_tool_calls([valid]), [valid])
        for payload in (
            "bad", [{"id": "", "function": valid["function"]}],
            [{"id": "call-1", "function": valid["function"]}] * 2,
            [valid] * 5, [{"id": "call-2", "function": {"name": "../secret", "arguments": "{}"}}],
            [{"id": "call-2", "function": {"name": "get_record", "arguments": {}}}],
            [{"id": "call-2", "type": "different", "function": valid["function"]}],
        ):
            with self.subTest(payload=payload), self.assertRaises(DomainError):
                normalize_tool_calls(payload)

    def test_tool_results_strip_internal_tokens_and_nested_secrets(self):
        payload = {
            "id": "record", "public_url": "https://example.invalid/?quote=SECRET",
            "idempotency_key": "retry-secret", "workspace_id": "private-workspace",
            "nested": [{"public_token": "bearer", "api_key": "key123456",
                        "name": "Цена", "amount_kopecks": 12000}],
        }
        raw = tool_result_message(payload)
        result = json.loads(raw)
        self.assertNotIn("public_url", result)
        self.assertNotIn("idempotency_key", result)
        self.assertNotIn("public_token", result["nested"][0])
        self.assertNotIn("api_key", result["nested"][0])
        self.assertEqual(result["nested"][0]["amount_kopecks"], 12000)

    def test_background_session_revocation_during_provider_call_blocks_commit(self):
        owner, user_id = self.account("job-midflight-revocation")
        with patch.dict(os.environ, ASSISTANT_WORKER_SECRET=SECRET, OPENROUTER_API_KEY="test-only"):
            code, result = self.call("/assistant/jobs", "POST", {"text": "Проверь"}, owner,
                                     key="revoke-during-model")
            self.assertEqual(code, 202, result)
            job_id = result["job"]["id"]

            def revoke(_messages):
                with self.mod.db() as con:
                    con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                return {"content": "Нельзя сохранять"}

            with patch("backend.assistant.query_model", side_effect=revoke):
                self.assertEqual(self.call("/cron/assistant", token=worker_token())[0], 200)

        with self.mod.db() as con:
            row = con.execute("SELECT status,quota_refunded FROM assistant_jobs WHERE id=?", (job_id,)).fetchone()
            history = con.execute("SELECT count(*) FROM assistant_messages WHERE user_id=?", (user_id,)).fetchone()[0]
            proposals = con.execute("SELECT count(*) FROM assistant_actions WHERE user_id=?", (user_id,)).fetchone()[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["quota_refunded"], 1)
        self.assertEqual(history, 0)
        self.assertEqual(proposals, 0)

    def test_background_role_downgrade_during_provider_call_blocks_commit(self):
        owner, user_id = self.account("job-midflight-role")
        with patch.dict(os.environ, ASSISTANT_WORKER_SECRET=SECRET, OPENROUTER_API_KEY="test-only"):
            code, result = self.call("/assistant/jobs", "POST", {"text": "Проверь"}, owner,
                                     key="downgrade-during-model")
            self.assertEqual(code, 202, result)
            job_id = result["job"]["id"]

            def downgrade(_messages):
                with self.mod.db() as con:
                    con.execute("UPDATE workspace_members SET role='viewer' WHERE user_id=?", (user_id,))
                return {"content": "Нельзя сохранять"}

            with patch("backend.assistant.query_model", side_effect=downgrade):
                self.assertEqual(self.call("/cron/assistant", token=worker_token())[0], 200)

        with self.mod.db() as con:
            row = con.execute("SELECT status,quota_refunded FROM assistant_jobs WHERE id=?", (job_id,)).fetchone()
            history = con.execute("SELECT count(*) FROM assistant_messages WHERE user_id=?", (user_id,)).fetchone()[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["quota_refunded"], 1)
        self.assertEqual(history, 0)


if __name__ == "__main__":
    unittest.main()
