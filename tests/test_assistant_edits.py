import concurrent.futures
import copy
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.assistant_edits import prepare_bulk, prepare_structure
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

    def test_insert_review_apply_replay_and_undo_preserve_existing_properties(self):
        owner, _ = self.account('ai-insert')
        quote = self.quote(owner)
        addition = {'name': 'Подготовка стен', 'unit': 'м²', 'quantity': '1.25', 'unit_price': 10005, 'cost_price': 6000}
        action = self.propose(owner, 'restructure_quote_items', {'id': quote['id'], 'operation': 'insert', 'after': 1,
                              'items': [addition], '_undo_fields': {'items': []}, '_preview': {'after_total': 0}})
        preview = action['preview']
        self.assertEqual(preview['kind'], 'quote_structure')
        self.assertEqual(preview['after_count'], 4)
        self.assertEqual(preview['rows'][0]['after_row'], 2)
        self.assertEqual(preview['rows'][0]['after']['subtotal'], 12506)
        self.assertEqual(preview['after_total'], quote['amount_kopecks'] + 12506)
        self.assertEqual(self.call('/quotes/' + quote['id'], token=owner)[1]['quote']['items'], quote['items'])
        first = self.call('/assistant/confirm', 'POST', {'id': action['id']}, owner)
        self.assertEqual(first[0], 200, first)
        self.assertEqual(first, self.call('/assistant/confirm', 'POST', {'id': action['id']}, owner))
        changed = first[1]['result']['quote']
        self.assertEqual([changed['items'][i] for i in (0, 2, 3)], quote['items'])
        self.assertTrue(first[1]['undoable'])
        self.assertEqual(self.call('/assistant/undo', 'POST', {'id': action['id']}, owner)[0], 200)
        self.assertEqual(self.call('/quotes/' + quote['id'], token=owner)[1]['quote']['items'], quote['items'])

    def test_remove_optional_row_and_reorder_are_reversible(self):
        owner, _ = self.account('ai-structure')
        quote = self.quote(owner)
        for operation, order in (('remove', [2]), ('reorder', [3, 1, 2])):
            action = self.propose(owner, 'restructure_quote_items', {'id': quote['id'], 'operation': operation, 'rows': order})
            self.assertEqual(action['preview']['after_total'], quote['amount_kopecks'])
            result = self.call('/assistant/confirm', 'POST', {'id': action['id']}, owner)
            self.assertEqual(result[0], 200, result)
            changed = result[1]['result']['quote']['items']
            self.assertEqual(changed, [quote['items'][i - 1] for i in ([1, 3] if operation == 'remove' else order)])
            self.assertEqual(self.call('/assistant/undo', 'POST', {'id': action['id']}, owner)[0], 200)
            self.assertEqual(self.call('/quotes/' + quote['id'], token=owner)[1]['quote']['items'], quote['items'])

    def test_structure_rejects_bad_rows_missing_price_bounds_and_simple_quote(self):
        owner, _ = self.account('ai-structure-validation')
        quote = self.quote(owner)
        service = SimpleNamespace(get=lambda *args: quote, quote_view=lambda record: copy.deepcopy(record))
        cases = [dict(operation='insert', items=[{'name': 'Без цены'}]),
                 dict(operation='insert', items=[{'name': 'Цена', 'unit_price': -1}]),
                 dict(operation='insert', items=[{'name': 'Цена', 'unit_price': 1}], after=True),
                 dict(operation='insert', items=[{'name': 'Цена', 'unit_price': 1}] * 51),
                 dict(operation='remove', rows=[1, 2, 3]), dict(operation='remove', rows=[1, 1]),
                 dict(operation='remove', rows=[True]), dict(operation='remove', rows=[4]),
                 dict(operation='reorder', rows=[1, 2]), dict(operation='reorder', rows=[1, 1, 3]),
                 dict(operation='reorder', rows=[True, 2, 3]), dict(operation='reorder', rows=[1, 2, 3])]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(DomainError):
                prepare_structure(service, {'id': quote['id'], **data})
        quote['itemized'] = False
        with self.assertRaises(DomainError):
            prepare_structure(service, {'id': quote['id'], 'operation': 'remove', 'rows': [2]})

    def test_structure_stale_confirm_stale_undo_and_published_draft_are_guarded(self):
        owner, _ = self.account('ai-structure-conflict')
        quote = self.quote(owner)
        action = self.propose(owner, 'restructure_quote_items', {'id': quote['id'], 'operation': 'remove', 'rows': [2]})
        quote = self.call('/quotes/' + quote['id'], 'PATCH', {'revision': quote['revision'], 'title': 'Правка'}, owner)[1]['quote']
        self.assertEqual(self.call('/assistant/confirm', 'POST', {'id': action['id']}, owner)[0], 409)
        fresh = self.propose(owner, 'restructure_quote_items', {'id': quote['id'], 'operation': 'reorder', 'rows': [3, 2, 1]})
        self.assertEqual(self.call('/assistant/confirm', 'POST', {'id': fresh['id']}, owner)[0], 200)
        changed = self.call('/quotes/' + quote['id'], token=owner)[1]['quote']
        changed = self.call('/quotes/' + quote['id'], 'PATCH', {'revision': changed['revision'], 'title': 'Следующая правка'}, owner)[1]['quote']
        self.assertEqual(self.call('/assistant/undo', 'POST', {'id': fresh['id']}, owner)[0], 409)
        self.assertEqual(self.call('/quotes/' + quote['id'], token=owner)[1]['quote'], changed)
        self.call('/quotes/' + quote['id'] + '/publish', 'POST', {}, owner)
        service = SimpleNamespace(get=lambda *args: {**changed, 'approval_state': 'sent'}, quote_view=lambda record: record)
        with self.assertRaises(DomainError):
            prepare_structure(service, {'id': quote['id'], 'operation': 'remove', 'rows': [2]})

    def test_structure_parallel_confirm_undo_and_foreign_owner(self):
        owner, _ = self.account('ai-structure-parallel')
        stranger, _ = self.account('ai-structure-outsider')
        quote = self.quote(owner)
        action = self.propose(owner, 'restructure_quote_items', {'id': quote['id'], 'operation': 'insert', 'items': [{'name': 'Доставка', 'unit_price': 5000}]})
        self.assertEqual(self.call('/assistant/confirm', 'POST', {'id': action['id']}, stranger)[0], 404)
        for path in ('confirm', 'undo'):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: self.call('/assistant/' + path, 'POST', {'id': action['id']}, owner), range(2)))
            self.assertTrue(all(code == 200 for code, _ in responses), responses)
            self.assertEqual(responses[0], responses[1])
        self.assertEqual(self.call('/quotes/' + quote['id'], token=owner)[1]['quote']['items'], quote['items'])

    def test_optional_selection_has_boolean_preview_and_changes_total_only_after_confirm(self):
        owner, _ = self.account('ai-option')
        quote = self.quote(owner)
        action = self.propose(owner, 'bulk_quote_items', {'id': quote['id'], 'rows': [2], 'field': 'included', 'value': True})
        self.assertFalse(action['preview']['rows'][0]['before'])
        self.assertTrue(action['preview']['rows'][0]['after'])
        self.assertEqual(action['preview']['after_total'], quote['amount_kopecks'] + 80000)
        result = self.call('/assistant/confirm', 'POST', {'id': action['id']}, owner)
        self.assertEqual(result[0], 200, result)
        self.assertEqual(result[1]['result']['quote']['amount_kopecks'], quote['amount_kopecks'] + 80000)
        self.assertEqual(self.call('/assistant/undo', 'POST', {'id': action['id']}, owner)[0], 200)
        service = SimpleNamespace(get=lambda *args: quote, quote_view=lambda record: copy.deepcopy(record))
        for bad in ({'value': 'true'}, {'value': 1}, {'operation': 'multiply', 'value': True}, {'rows': [1], 'value': False}):
            with self.subTest(bad=bad), self.assertRaises(DomainError):
                prepare_bulk(service, {'id': quote['id'], 'rows': [2], 'field': 'included', 'value': True, **bad})

    def test_structure_background_worker_only_persists_reviewable_proposal(self):
        from tests.test_assistant_jobs import SECRET, worker_token
        owner, _ = self.account('ai-structure-job')
        quote = self.quote(owner)
        with patch.dict(os.environ, ASSISTANT_WORKER_SECRET=SECRET, OPENROUTER_API_KEY='test-only'):
            code, queued = self.call('/assistant/jobs', 'POST', {'text': 'Добавь доставку', 'context': {'entity': 'quotes', 'id': quote['id']}}, owner, key='structure-job')
            self.assertEqual(code, 202, queued)
            with patch('backend.assistant.query_model', return_value=self.tool('restructure_quote_items', {'id': quote['id'], 'operation': 'insert', 'items': [{'name': 'Доставка', 'unit_price': 5000}]})):
                self.assertEqual(self.call('/cron/assistant', token=worker_token())[0], 200)
            job = self.call('/assistant/jobs/' + queued['job']['id'], token=owner)[1]['job']
        self.assertEqual(job['status'], 'completed')
        action = job['result']['actions'][0]
        self.assertEqual(action['preview']['after_count'], 4)
        self.assertEqual(self.call('/quotes/' + quote['id'], token=owner)[1]['quote']['items'], quote['items'])
        self.assertEqual(self.call('/assistant/confirm', 'POST', {'id': action['id']}, owner)[0], 200)

    def test_structure_two_hundred_rows_reorders_without_losing_data_and_blocks_overflow(self):
        owner, _ = self.account('ai-structure-200')
        code, result = self.call('/quotes', 'POST', {'title': 'Большая смета', 'client': 'Клиент', 'items': [
            {'name': f'Позиция {i}', 'unit_price': 101, 'quantity': '0.5', 'category': 'Тест'} for i in range(200)]}, owner)
        self.assertEqual(code, 201, result)
        quote = result['quote']
        service = SimpleNamespace(get=lambda *args: quote, quote_view=lambda record: copy.deepcopy(record))
        changed = prepare_structure(service, {'id': quote['id'], 'operation': 'reorder', 'rows': list(range(200, 0, -1))})
        self.assertEqual(changed['items'], list(reversed(quote['items'])))
        self.assertEqual(changed['_preview']['after_total'], quote['amount_kopecks'])
        with self.assertRaises(DomainError):
            prepare_structure(service, {'id': quote['id'], 'operation': 'insert', 'items': [{'name': 'Переполнение', 'unit_price': 1}]})

    def test_insertion_positions_and_excluded_options_keep_currency_and_decimal_math(self):
        owner, _ = self.account('ai-structure-currency')
        quote = self.quote(owner)
        quote['currency'] = 'USD'
        service = SimpleNamespace(get=lambda *args: quote, quote_view=lambda record: copy.deepcopy(record))
        for after in (0, 3):
            action = prepare_structure(service, {'id': quote['id'], 'operation': 'insert', 'after': after, 'items': [
                {'name': 'Опция', 'unit_price': 10005, 'quantity': '1.25', 'optional': True, 'included': False}]})
            self.assertEqual(action['_preview']['currency'], 'USD')
            self.assertEqual(action['_preview']['after_total'], quote['amount_kopecks'])
            self.assertEqual(action['items'][after]['subtotal'], 12506)
