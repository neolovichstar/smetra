"""Security and contract tests for structured AI estimate drafts."""
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import ai
from backend.business import DomainError
from backend.legal import TERMS_VERSION, has_current_terms


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit=-1):
        return self.payload[:limit] if limit >= 0 else self.payload


class FakeHandler:
    def throttle(self, *args):
        return None


class FakeService:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(
            """
            CREATE TABLE ai_usage (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.user = {"id": "test-user"}
        self.wid = "test-workspace"
        self.h = FakeHandler()

    def emit(self, *args):
        return None


def model_response(description="Снять старое плиточное покрытие", title="Ремонт ванной"):
    document = {
        "title": title,
        "client": "",
        "description": "",
        "terms": "",
        "items": [
            {
                "name": "Демонтаж плитки",
                "description": description,
                "quantity": "12",
                "unit": "м²",
                "unit_price": 0,
            }
        ],
    }
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps(document, ensure_ascii=False)},
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 34},
    }


class AIEstimateGuardrailsTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()

    def tearDown(self):
        self.service.con.close()

    def call_draft(self, model_payload):
        with (
            patch.dict("os.environ", {
                "OPENROUTER_API_KEY": "test-key",
                "OPENROUTER_MODEL": "openrouter/free",
            }),
            patch("backend.ai.urllib.request.urlopen", return_value=FakeResponse(model_payload)),
        ):
            return ai._draft(self.service, {"text": "Ремонт ванной комнаты"})

    def test_structured_draft_keeps_math_out_of_llm_and_marks_measurement(self):
        status, response = self.call_draft(model_response())
        draft = response["draft"]
        self.assertEqual(status, 200)
        self.assertTrue(response["requires_review"])
        self.assertEqual(response["calculation_source"], "smetra_deterministic")
        self.assertEqual(draft["ai_generated"], 1)
        self.assertEqual(
            set(draft["items"][0]),
            {"name", "description", "quantity", "unit", "unit_price"},
        )
        self.assertEqual(draft["items"][0]["unit_price"], 0)
        self.assertIn("Требует замера по месту", draft["items"][0]["description"])
        self.assertNotIn("total", json.dumps(draft).lower())

    def test_model_total_in_free_text_is_rejected(self):
        payload = model_response(description="Итого ремонт ванной составит 150 000 руб.")
        with self.assertRaises(DomainError) as error:
            self.call_draft(payload)
        self.assertEqual(error.exception.status, 502)

    def test_terms_consent_is_versioned(self):
        accepted = {"terms_accepted_at": 12345, "terms_version": TERMS_VERSION}
        self.assertTrue(has_current_terms(accepted))
        self.assertFalse(has_current_terms({"terms_accepted_at": 12345, "terms_version": "old"}))
        self.assertFalse(has_current_terms({"terms_accepted_at": 0, "terms_version": TERMS_VERSION}))
        self.assertFalse(has_current_terms(None))

    def test_postgres_migration_is_additive_and_versioned(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "supabase"
            / "migrations"
            / "20261019190000_ai_estimate_legal_guardrails.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS terms_accepted_at BIGINT NOT NULL DEFAULT 0", migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS terms_version TEXT NOT NULL DEFAULT ''", migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS ai_generated BIGINT NOT NULL DEFAULT 0", migration)
        self.assertIn("ALTER COLUMN terms_accepted_at SET DEFAULT 0", migration)
        self.assertIn("VALUES (36, extract(epoch FROM now())::BIGINT)", migration)
        self.assertNotIn("DROP TABLE", migration.upper())


if __name__ == "__main__":
    unittest.main()
