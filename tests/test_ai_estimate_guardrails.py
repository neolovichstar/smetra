import json
import os
import sqlite3
import unittest
from unittest.mock import patch

from backend import ai


class Handler:
    def throttle(self, *args):
        return None


class FakeService:
    def __init__(self, con):
        self.con = con
        self.user = {"id": "user-1"}
        self.wid = "workspace-1"
        self.h = Handler()
        self.events = []

    def emit(self, *args, **kwargs):
        self.events.append(args)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return json.dumps(self.payload).encode("utf-8")


class AIEstimateGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(
            "CREATE TABLE ai_usage (id TEXT PRIMARY KEY,workspace_id TEXT,user_id TEXT,"
            "action TEXT,model TEXT,status TEXT,created_at INTEGER,input_tokens INTEGER DEFAULT 0,"
            "output_tokens INTEGER DEFAULT 0)"
        )
        self.service = FakeService(self.con)

    def tearDown(self):
        self.con.close()

    def run_draft(self, items):
        model_output = {
            "title": "Черновик работ", "client": "",
            "description": "Предварительный состав", "terms": "", "items": items,
        }
        provider = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(model_output, ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        }
        with patch.object(ai, "available", return_value=True), patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "test-only", "OPENROUTER_MODEL": "openrouter/free"},
        ), patch.object(ai.urllib.request, "urlopen", return_value=Response(provider)) as opener:
            status, result = ai._draft(self.service, {"text": "Ремонт ванной"})
        request = json.loads(opener.call_args.args[0].data.decode("utf-8"))
        return status, result, request

    def test_provider_schema_is_only_line_items_and_system_forbids_totals(self):
        status, result, request = self.run_draft([{
            "name": "Грунтовка стен", "description": "Подготовка поверхности",
            "quantity": "12", "unit": "м²", "unit_price": 8500,
        }])
        self.assertEqual(status, 200)
        schema = request["response_format"]["json_schema"]["schema"]
        self.assertEqual(set(schema["properties"]), {"title", "client", "description", "terms", "items"})
        item_schema = schema["properties"]["items"]["items"]
        self.assertEqual(set(item_schema["properties"]), {"name", "description", "quantity", "unit", "unit_price"})
        self.assertNotIn("total", str(schema).lower())
        system = request["messages"][0]["content"].lower()
        self.assertIn("черновой ассистент-структуризатор", system)
        self.assertIn("не вычисляй", system)
        self.assertIn("требует замера по месту", system)
        draft = result["draft"]
        self.assertNotIn("total", draft)
        self.assertNotIn("amount_kopecks", draft)
        self.assertEqual(draft["items"][0]["unit_price"], 8500)
        self.assertIn("Требует замера по месту", draft["items"][0]["description"])
        self.assertIn("предварительным черновиком", draft["disclaimer"])

    def test_unknown_price_stays_zero_and_model_cannot_return_calculated_sums(self):
        status, result, _ = self.run_draft([{
            "name": "Демонтаж старой плитки", "description": "",
            "quantity": "1", "unit": "усл.", "unit_price": 0,
        }])
        self.assertEqual(status, 200)
        item = result["draft"]["items"][0]
        self.assertEqual(item["unit_price"], 0)
        self.assertEqual(set(item), {"name", "description", "quantity", "unit", "unit_price"})
        self.assertIn("Требует замера по месту", item["description"])
        self.assertNotIn("total", result["draft"])
        self.assertNotIn("subtotal", result["draft"])


if __name__ == "__main__":
    unittest.main()
