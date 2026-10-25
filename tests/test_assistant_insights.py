"""Regression tests for the expanded workspace-scoped assistant toolbox."""

import datetime as dt
import json
import os
import unittest
from unittest.mock import patch

from backend.assistant import tool_result_message, tools, validate_tool_arguments
from backend.business import DomainError
from tests import test_business


class AssistantInsightToolsTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    @staticmethod
    def tool(name, args, call_id="ai-read"):
        return {"content": None, "tool_calls": [{
            "id": call_id, "type": "function", "function": {
                "name": name, "arguments": json.dumps(args, ensure_ascii=False),
            },
        }]}

    def read(self, token, name, args):
        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"), patch(
            "backend.assistant.query_model",
            side_effect=[self.tool(name, args), {"content": "Проверено", "tool_calls": []}],
        ) as provider:
            status, result = self.call("/assistant/chat", "POST", {"text": "Проверь данные"}, token)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["actions"], [])
        return json.loads(provider.call_args_list[1].args[0][-1]["content"])

    def test_catalog_search_history_and_tenant_isolation(self):
        owner, _ = self.account("insights-catalog-owner")
        stranger, _ = self.account("insights-catalog-stranger")
        code, created = self.call("/catalog", "POST", {
            "name": "Штукатурка машинная", "price": 12000, "unit": "м²",
        }, owner)
        self.assertEqual(code, 201, created)
        record_id = created["item"]["id"]

        prices = self.read(owner, "find_catalog_prices", {"query": "Штукатурка"})
        self.assertEqual(prices["items"][0]["id"], record_id)
        self.assertEqual(prices["items"][0]["price"], 12000)
        self.assertEqual(prices["price_unit"], "kopecks")
        self.assertEqual(self.read(stranger, "find_catalog_prices",
                                  {"query": "Штукатурка"})["items"], [])

        history = self.read(owner, "catalog_price_history", {"id": record_id})
        self.assertEqual(history["item"]["id"], record_id)
        forbidden = self.read(stranger, "catalog_price_history", {"id": record_id})
        self.assertIn("error", forbidden)

        search = self.read(owner, "search_workspace", {"query": "Штукатурка"})
        self.assertIn(record_id, [item["id"] for item in search["results"]])

    def test_quote_audit_uses_server_total_not_model_arithmetic(self):
        owner, _ = self.account("insights-quote-owner")
        quote = self.call("/quotes", "POST", {
            "title": "Ванная", "client": "Заказчик",
            "items": [
                {"name": "Работы", "unit": "м²", "unit_price": 10505, "quantity": "2.5"},
                {"name": "Бесплатная услуга", "unit": "шт", "unit_price": 0, "quantity": "1"},
            ],
        }, owner)[1]["quote"]
        audit = self.read(owner, "audit_quote", {"id": quote["id"]})
        self.assertEqual(audit["amount_kopecks"], quote["amount_kopecks"])
        self.assertEqual(audit["totals_source"], "server_authoritative")
        self.assertEqual(audit["item_count"], 2)
        self.assertIn({"row": 2, "issue": "zero_price"}, audit["issues"])
        self.assertEqual(audit["revision"], quote["revision"])

    def test_project_finances_scoped_and_deadline_radar(self):
        owner, _ = self.account("insights-project-owner")
        other, _ = self.account("insights-project-other")
        code, result = self.call("/projects", "POST",
                                 {"name": "Квартира", "amount_kopecks": 250000}, owner)
        self.assertEqual(code, 201, result)
        project_id = result["item"]["id"]
        finances = self.read(owner, "project_finances", {"id": project_id})
        self.assertEqual(finances["planned_revenue_kopecks"], 250000)
        self.assertEqual(finances["paid_kopecks"], 0)
        self.assertEqual(finances["unpaid_kopecks"], 250000)
        self.assertIn("error", self.read(other, "project_finances", {"id": project_id}))

        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        task = self.call("/tasks", "POST", {
            "name": "Проверить материалы", "due_date": yesterday,
        }, owner)[1]["item"]
        deadlines = self.read(owner, "deadline_radar", {"days": 7})
        self.assertIn(task["id"], [row["id"] for row in deadlines["deadlines"]])
        self.assertTrue(next(x for x in deadlines["deadlines"] if x["id"] == task["id"])["overdue"])
        self.assertNotIn(task["id"], [row["id"] for row in
                         self.read(other, "deadline_radar", {"days": 7})["deadlines"]])

    def test_validation_rejects_unknown_functions_extra_fields_and_bad_types(self):
        names = {t["function"]["name"] for t in tools()}
        for name in ("audit_quote", "find_catalog_prices", "project_finances", "deadline_radar",
                     "compare_quote_versions", "catalog_price_history", "search_workspace"):
            self.assertIn(name, names)
        for name, args in (
            ("unknown_function", {}),
            ("get_record", {"entity": "quotes", "id": "a", "unexpected": 1}),
            ("deadline_radar", {"days": True}),
            ("deadline_radar", {"days": 366}),
            ("audit_quote", {}),
            ("create_clients", {"name": ["bad"]}),
        ):
            with self.subTest(name=name, args=args), self.assertRaises(DomainError):
                validate_tool_arguments(name, args)
        validate_tool_arguments("deadline_radar", {"days": 30})
        validate_tool_arguments("audit_quote", {"id": "a"})

    def test_truncated_tool_output_is_always_valid_json(self):
        message = tool_result_message({"items": ["a" * 1000] * 50})
        self.assertLessEqual(len(message), 6000)
        self.assertTrue(json.loads(message)["truncated"])

    def test_three_step_search_read_prepare_chain(self):
        owner, _ = self.account("insights-chain")
        client = self.call("/clients", "POST", {"name": "Проверенный клиент"}, owner)[1]["item"]
        responses = [
            self.tool("list_records", {"entity": "clients", "search": "Проверенный"}, "c1"),
            self.tool("get_record", {"entity": "clients", "id": client["id"]}, "c2"),
            self.tool("create_tasks", {"name": "Позвонить клиенту"}, "c3"),
        ]
        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"), patch(
            "backend.assistant.query_model", side_effect=responses,
        ) as provider:
            status, result = self.call("/assistant/chat", "POST",
                                       {"text": "Найди клиента и предложи задачу"}, owner)
        self.assertEqual(status, 200, result)
        self.assertEqual(provider.call_count, 3)
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["tool"], "create_tasks")
        self.assertEqual(self.call("/tasks", token=owner)[1]["items"], [])


if __name__ == "__main__":
    unittest.main()
