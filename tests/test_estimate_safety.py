"""Server-side regression tests for safe AI estimate drafting and consent."""
import json
import os
import unittest
from unittest.mock import patch

from tests.test_business import BusinessFlows


class _Lease:
    def release(self):
        pass


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.payload[:size]


class EstimateSafetyTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp
    call = BusinessFlows.call
    account = BusinessFlows.account

    def test_email_registration_requires_explicit_versioned_consent(self):
        status, result = self.call(
            "/auth/register",
            "POST",
            {
                "email": "no-consent@test.invalid",
                "name": "No consent",
                "password": "secure twelve password",
            },
        )
        self.assertEqual(status, 400, result)
        self.assertIn("условия", result["error"].lower())

    def test_ai_endpoints_cannot_bypass_server_side_consent(self):
        token, user_id = self.account("consent-gate")
        with self.mod.db() as con:
            con.execute("DELETE FROM legal_acceptances WHERE user_id=?", (user_id,))

        status, result = self.call("/me/legal-consent", token=token)
        self.assertEqual(status, 200, result)
        self.assertFalse(result["accepted"])

        status, result = self.call(
            "/ai/draft", "POST", {"text": "Ремонт ванной"}, token
        )
        self.assertEqual(status, 428, result)

        status, result = self.call(
            "/me/legal-consent",
            "POST",
            {"accepted": True, "version": "older-version"},
            token,
        )
        self.assertEqual(status, 400, result)

        status, result = self.call(
            "/me/legal-consent",
            "POST",
            {"accepted": True, "version": "2026-10-19-ai-estimate-v1"},
            token,
        )
        self.assertEqual(status, 200, result)
        self.assertTrue(result["accepted"])

        with self.mod.db() as con:
            rows = con.execute(
                "SELECT document_version,source FROM legal_acceptances WHERE user_id=?",
                (user_id,),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["document_version"], "2026-10-19-ai-estimate-v1")
        self.assertEqual(rows[0]["source"], "first_estimate")

    def test_ai_draft_is_structured_and_hidden_work_is_marked_for_measurement(self):
        token, _ = self.account("structured-draft")
        model_result = {
            "title": "Ремонт ванной",
            "client": "",
            "description": "Предварительный перечень, требует проверки",
            "terms": "Проверить объёмы и технологию на объекте",
            "items": [
                {
                    "name": "Демонтаж плитки",
                    "description": "Снять существующую облицовку",
                    "quantity": "12",
                    "unit": "м²",
                    "unit_price": 0,
                    "requires_measurement": False,
                },
                {
                    "name": "Грунтовка стен",
                    "description": "Подготовка основания перед отделкой",
                    "quantity": "12",
                    "unit": "м²",
                    "unit_price": 3500,
                    "requires_measurement": True,
                },
            ],
        }
        wire = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(model_result, ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 50, "completion_tokens": 80},
        }
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-only", OPENROUTER_MODEL="openrouter/free"),
            patch("backend.redis_infra.acquire_lock", return_value=_Lease()),
            patch("backend.ai.urllib.request.urlopen", return_value=_Response(wire)) as opener,
        ):
            status, result = self.call(
                "/ai/draft", "POST", {"text": "Подготовить ванную комнату"}, token
            )

        self.assertEqual(status, 200, result)
        self.assertTrue(result["requires_review"])
        draft = result["draft"]
        self.assertNotIn("total", draft)
        self.assertNotIn("amount_kopecks", draft)
        self.assertEqual(
            set(draft["items"][0]),
            {"name", "description", "quantity", "unit", "unit_price", "requires_measurement"},
        )
        self.assertTrue(draft["items"][0]["requires_measurement"])
        self.assertIn("Требует замера по месту", draft["items"][0]["description"])
        self.assertTrue(draft["items"][1]["requires_measurement"])
        self.assertIn("Требует замера по месту", draft["items"][1]["description"])

        payload = json.loads(opener.call_args.args[0].data)
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        schema = payload["response_format"]["json_schema"]["schema"]
        self.assertTrue(schema["additionalProperties"] is False)
        self.assertNotIn("total", schema["properties"])
        self.assertIn("requires_measurement", schema["properties"]["items"]["items"]["properties"])
        self.assertIn("черновой ассистент-структуризатор", payload["messages"][0]["content"])
        self.assertIn("итоговую сумму", payload["messages"][0]["content"])

    def test_model_cannot_smuggle_a_total_into_the_structured_schema(self):
        token, _ = self.account("draft-total-rejected")
        model_result = {
            "title": "Ремонт",
            "client": "",
            "description": "Черновик",
            "terms": "",
            "total": 15000000,
            "items": [{
                "name": "Работа",
                "description": "",
                "quantity": "1",
                "unit": "шт.",
                "unit_price": 15000000,
                "requires_measurement": False,
            }],
        }
        wire = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(model_result, ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 20},
        }
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-only", OPENROUTER_MODEL="openrouter/free"),
            patch("backend.redis_infra.acquire_lock", return_value=_Lease()),
            patch("backend.ai.urllib.request.urlopen", return_value=_Response(wire)),
        ):
            status, result = self.call(
                "/ai/draft", "POST", {"text": "Составь смету"}, token
            )
        self.assertEqual(status, 502, result)
        self.assertIn("черновик", result["error"].lower())


    def test_model_cannot_hide_a_final_sum_inside_narrative_text(self):
        token, _ = self.account("draft-narrative-total")
        model_result = {
            "title": "Ремонт ванной",
            "client": "",
            "description": "Итого ремонт ванной обойдётся в 150 000 рублей.",
            "terms": "",
            "items": [{
                "name": "Укладка плитки",
                "description": "Укладка напольной плитки",
                "quantity": "12",
                "unit": "м²",
                "unit_price": 350000,
                "requires_measurement": False,
            }],
        }
        wire = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(model_result, ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 20},
        }
        with (
            patch.dict(os.environ, OPENROUTER_API_KEY="test-only", OPENROUTER_MODEL="openrouter/free"),
            patch("backend.redis_infra.acquire_lock", return_value=_Lease()),
            patch("backend.ai.urllib.request.urlopen", return_value=_Response(wire)),
        ):
            status, result = self.call(
                "/ai/draft", "POST", {"text": "Ремонт ванной"}, token
            )
        self.assertEqual(status, 502, result)
        self.assertIn("черновик", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
