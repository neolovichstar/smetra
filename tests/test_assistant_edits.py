import concurrent.futures
import copy
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.assistant_edits import prepare_bulk
from backend.business import DomainError
from tests import test_business


class AssistantEditTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def quote(self, token):
        return self.call("/quotes", "POST", {"title": "Отделка", "client": "Клиент", "items": [
            {"name": "Покраска", "unit_price": 10005, "cost_price": 7000,
             "quantity": "2.5", "tax": "10", "category": "Стены"},
            {"name": "Опция", "unit_price": 80000, "quantity": "1", "optional": True, "included": False},
            {"name": "Доставка", "unit_price": 150000, "quantity": "1", "unit": "усл."},
        ]}, token)[1]["quote"]

    @staticmethod
    def tool(name, arguments):
        return {"content": None, "tool_calls": [{"id": "edit-call", "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)}}]}

    def propose(self, token, name, arguments):
        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"), patch(
            "backend.assistant.query_model", return_value=self.tool(name, arguments),
        ):
            status, result = self.call("/assistant/chat", "POST", {"text": "Измени выбранные строки"}, token)
        self.assertEqual(status, 200, result)
        return result["actions"][0]

    def bulk(self, token, quote):
        return self.propose(token, "bulk_quote_items", {"id": quote["id"], "rows": [1, 2],
                "field": "unit_price", "operation": "multiply", "value": "1.1"})

    def test_bulk_preview_preserves_unselected_rows_and_rounds_money(self):
        owner, _ = self.account("ai-bulk-preview")
        quote = self.quote(owner)
        action = self.bulk(owner, quote)
        self.assertNotIn("_undo_fields", action["arguments"])
        self.assertEqual(action["arguments"]["items"][0]["unit_price"], 11006)
        self.assertEqual(action["arguments"]["items"][0]["cost_price"], 7000)
        self.assertEqual(action["arguments"]["items"][2], quote["items"][2])
        preview = action["preview"]
        self.assertEqual([row["row"] for row in preview["rows"]], [1, 2])
        self.assertEqual(preview["before_total"], quote["amount_kopecks"])
        self.assertGreater(preview["after_total"], preview["before_total"])
        self.assertEqual(self.call("/quotes/" + quote["id"], token=owner)[1]["quote"], quote)
        pending = self.call("/assistant", token=owner)[1]["actions"][0]
        self.assertEqual(pending["preview"], preview)
        self.assertNotIn("_undo_fields", pending["arguments"])

    def test_bulk_apply_and_concurrent_undo_are_idempotent(self):
        owner, _ = self.account("ai-bulk-undo")
        quote = self.quote(owner)
        action = self.bulk(owner, quote)
        first = self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)
        self.assertEqual(first[0], 200, first)
        self.assertTrue(first[1]["undoable"])
        self.assertEqual(first, self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner))
        changed = self.call("/quotes/" + quote["id"], token=owner)[1]["quote"]
        self.assertEqual(changed["amount_kopecks"], action["preview"]["after_total"])
        self.assertEqual(changed["revision"], quote["revision"] + 1)
        self.assertEqual(self.call("/assistant", token=owner)[1]["recent_actions"][0]["id"], action["id"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            reverted = list(pool.map(lambda _: self.call("/assistant/undo", "POST", {"id": action["id"]}, owner), range(2)))
        self.assertEqual(reverted[0], reverted[1])
        self.assertEqual(reverted[0][0], 200, reverted)
        restored = self.call("/quotes/" + quote["id"], token=owner)[1]["quote"]
        self.assertEqual(restored["items"], quote["items"])
        self.assertEqual(restored["amount_kopecks"], quote["amount_kopecks"])
        self.assertEqual(restored["revision"], quote["revision"] + 2)
        self.assertEqual(self.call("/assistant", token=owner)[1]["recent_actions"], [])
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)[0], 409)

    def test_manual_changes_block_stale_apply_and_undo(self):
        owner, _ = self.account("ai-bulk-conflict")
        quote = self.quote(owner)
        action = self.bulk(owner, quote)
        quote = self.call("/quotes/" + quote["id"], "PATCH", {"revision": quote["revision"], "title": "Правка вручную"}, owner)[1]["quote"]
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)[0], 409)
        fresh = self.bulk(owner, quote)
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": fresh["id"]}, owner)[0], 200)
        quote = self.call("/quotes/" + quote["id"], token=owner)[1]["quote"]
        quote = self.call("/quotes/" + quote["id"], "PATCH", {"revision": quote["revision"], "title": "Новая ручная правка"}, owner)[1]["quote"]
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": fresh["id"]}, owner)[0], 409)
        self.assertEqual(self.call("/quotes/" + quote["id"], token=owner)[1]["quote"], quote)

    def test_action_owner_isolation_and_expired_undo(self):
        owner, _ = self.account("ai-bulk-owner")
        outsider, _ = self.account("ai-bulk-stranger")
        quote = self.quote(owner)
        action = self.bulk(owner, quote)
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, outsider)[0], 404)
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, outsider)[0], 404)
        self.assertEqual(self.call("/assistant", token=outsider)[1]["actions"], [])
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)[0], 200)
        with self.mod.db() as con:
            result = json.loads(con.execute("SELECT result FROM assistant_actions WHERE id=?", (action["id"],)).fetchone()[0])
            result["undo_until"] = 1
            con.execute("UPDATE assistant_actions SET result=? WHERE id=?", (json.dumps(result), action["id"]))
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, owner)[0], 409)
        self.assertEqual(self.call("/assistant", token=owner)[1]["recent_actions"], [])

    def test_read_quote_exposes_rows_and_generic_client_update_is_reversible(self):
        owner, _ = self.account("ai-edit-client")
        quote = self.quote(owner)
        from backend.assistant import execute_read

        with self.mod.db() as con:
            from backend.business import Service
            service = object.__new__(Service)
            service.con, service.origin = con, "http://localhost"
            service.wid = con.execute("SELECT workspace_id FROM quotes WHERE id=?", (quote["id"],)).fetchone()[0]
            record = execute_read(service, "get_record", {"entity": "quotes", "id": quote["id"]})
        self.assertEqual([item["row"] for item in record["items"]], [1, 2, 3])
        client = self.call("/clients", "POST", {"name": "Иван", "notes": "Не изменять"}, owner)[1]["item"]
        action = self.propose(owner, "update_clients", {"id": client["id"], "name": "Иван Петров",
                              "_undo_fields": {"name": "Подмена"}})
        self.assertEqual(action["preview"]["rows"][0]["before"], "Иван")
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, owner)[0], 200)
        self.assertEqual(self.call("/assistant/undo", "POST", {"id": action["id"]}, owner)[0], 200)
        restored = self.call("/clients/" + client["id"], token=owner)[1]["item"]
        self.assertEqual(restored["name"], "Иван")
        self.assertEqual(restored["notes"], "Не изменять")

    def test_bulk_rejects_unsafe_inputs_and_published_quotes(self):
        owner, _ = self.account("ai-bulk-validation")
        quote = self.quote(owner)
        service = SimpleNamespace(get=lambda *args: quote, quote_view=lambda record: copy.deepcopy(record))
        valid = {"id": quote["id"], "rows": [1], "field": "unit_price", "value": "12345"}
        for override in ({"rows": []}, {"rows": [True]}, {"rows": [0]}, {"rows": [4]},
                         {"rows": [1, 1]}, {"rows": [1] * 51}, {"field": "status"},
                         {"value": "-1"}, {"value": True}, {"value": "1e50"},
                         {"field": "unit", "operation": "multiply", "value": "2"}):
            with self.subTest(override=override), self.assertRaises(DomainError):
                prepare_bulk(service, {**valid, **override})
        quote["approval_state"] = "sent"
        with self.assertRaises(DomainError) as error:
            prepare_bulk(service, valid)
        self.assertEqual(error.exception.status, 409)
