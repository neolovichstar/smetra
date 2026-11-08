"""AI-first estimates: creation through the assistant, deterministic money,
free manual editing at a zero balance and app actions offered as buttons."""
import json
import os
import time
import unittest
from unittest.mock import patch

from backend import ai_tokens
from backend.assistant_app_tools import calculate_material
from backend.business import DomainError
from backend.estimate_drafts import normalize
from tests.test_business import BusinessFlows

DRAFT = {
    "title": "Ремонт ванной 4 м²",
    "assumptions": ["Высота стен 2,5 м", "Плитка среднего класса"],
    "region": "Москва",
    "items": [
        {"name": "Демонтаж плитки", "quantity": "14", "unit": "м²", "unit_price": 45000,
         "category": "Демонтаж", "kind": "work", "price_status": "confirmed"},
        {"name": "Укладка плитки", "quantity": "14", "unit": "м²", "unit_price": 180000,
         "category": "Отделка", "kind": "work", "price_status": "estimate"},
        {"name": "Плитка керамическая", "quantity": "15.4", "unit": "м²", "unit_price": 0,
         "category": "Материалы", "kind": "material", "price_status": "unknown"},
        {"name": "Гидроизоляция", "quantity": "4.5", "unit": "м²", "unit_price": 33333,
         "category": "Демонтаж", "kind": "work", "price_status": "confirmed"},
    ],
}


def tool(name, arguments, call_id="call-1"):
    return {"content": None, "tool_calls": [{"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}


class DraftNormalisationTests(unittest.TestCase):
    def test_sections_totals_and_honest_price_labels(self):
        arguments, preview = normalize(DRAFT)
        # Sections keep the order in which they first appear; lines are grouped.
        self.assertEqual([s["name"] for s in preview["sections"]], ["Демонтаж", "Отделка", "Материалы"])
        self.assertEqual([i["name"] for i in arguments["items"]],
                         ["Демонтаж плитки", "Гидроизоляция", "Укладка плитки", "Плитка керамическая"])
        # 14 × 450 + 4.5 × 333.33 (rounded half up per line) + 14 × 1800 + 0
        self.assertEqual(preview["sections"][0]["subtotal"], 630000 + 149999)
        self.assertEqual(preview["total"], 630000 + 149999 + 2520000)
        self.assertEqual(preview["counts"], {"lines": 4, "works": 3, "materials": 1, "estimated": 1, "unknown": 1})
        self.assertIn("ориентировочная", arguments["items"][2]["description"])
        self.assertIn("неизвестна", arguments["items"][3]["description"])
        self.assertIn("Высота стен 2,5 м", arguments["description"])
        self.assertIn("не окончательный расчёт", arguments["description"])
        self.assertEqual(arguments["items"][3]["visual_role"], "material")

    def test_inconsistent_model_output_is_refused(self):
        bad_price = {**DRAFT, "items": [{**DRAFT["items"][2], "unit_price": 50000}]}
        with self.assertRaises(DomainError):
            normalize(bad_price)
        duplicate = {**DRAFT, "items": [DRAFT["items"][0], {**DRAFT["items"][0], "quantity": "2"}]}
        with self.assertRaises(DomainError) as raised:
            normalize(duplicate)
        self.assertEqual(raised.exception.status, 409)
        for broken in ({"quantity": "-1"}, {"quantity": "много"}, {"unit_price": 10.5}, {"kind": "tool"}, {"price_status": "maybe"}):
            with self.subTest(broken=broken), self.assertRaises(DomainError):
                normalize({**DRAFT, "items": [{**DRAFT["items"][0], **broken}]})
        with self.assertRaises(DomainError):
            normalize({**DRAFT, "items": []})


class CalculatorToolTests(unittest.TestCase):
    def test_material_calculators_match_the_web_formulas(self):
        tile = calculate_material("tile", {"length": "4", "width": "3", "pack": "1.44"})
        self.assertEqual((tile["result"]["value"], tile["packages"]["value"]), ("13.2", "10"))
        self.assertIn("Запас на подрезку", tile["defaults_used"])
        paint = calculate_material("paint", {"length": "5", "height": "2.7", "coats": "2", "coverage": "10", "pack": "2.5"})
        self.assertEqual((paint["result"]["value"], paint["packages"]["value"]), ("2.97", "2"))
        concrete = calculate_material("concrete", {"length": "5", "width": "3", "thickness": "10"})
        self.assertEqual(concrete["result"]["value"], "1.575")
        with self.assertRaises(DomainError):
            calculate_material("tile", {"length": "4", "width": "3"})
        with self.assertRaises(DomainError):
            calculate_material("paint", {"length": "1", "height": "1", "openings": "5", "coats": "1", "coverage": "1", "pack": "1"})


class ModelSelectionTests(unittest.TestCase):
    def test_claude_haiku_serves_every_plan_and_free_plan_stays_guarded(self):
        from types import SimpleNamespace
        from backend.assistant import CLAUDE_MODEL, _stream_payload, assistant_model
        free = SimpleNamespace(wid=None, user={"plan": "free", "entitlement_until": 0})
        paid = SimpleNamespace(wid=None, user={"plan": "pro", "entitlement_until": int(time.time()) + 3600})
        clean = {key: value for key, value in os.environ.items() if not key.startswith("OPENROUTER_")}
        with patch.dict(os.environ, clean, clear=True):
            self.assertEqual(CLAUDE_MODEL, "anthropic/claude-haiku-5.5")
            self.assertEqual(assistant_model(free), (CLAUDE_MODEL, False))
            self.assertEqual(assistant_model(free, has_image=True), (CLAUDE_MODEL, False))
            self.assertEqual(assistant_model(paid), (CLAUDE_MODEL, True))
            payload = _stream_payload(CLAUDE_MODEL, [{"role": "user", "content": "x"}], False)
            self.assertNotIn("temperature", payload)  # Haiku 5.5 rejects non-default sampling
            self.assertIn("temperature", _stream_payload("some/vendor:free", [], False))
        with patch.dict(os.environ, {**clean, "OPENROUTER_MODEL": "anthropic/claude-opus-5.5"}, clear=True):
            with self.assertRaises(DomainError):
                assistant_model(free)


class AiEstimateFlowTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp
    call = BusinessFlows.call
    account = BusinessFlows.account

    def chat(self, token, reply, text="Составь смету"):
        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"), patch(
            "backend.assistant.query_model", side_effect=reply if callable(reply) else None,
            return_value=None if callable(reply) else reply,
        ):
            return self.call("/assistant/chat", "POST", {"text": text}, token)

    def exhaust(self, user_id):
        with self.mod.db() as con:
            con.execute(
                "INSERT INTO rate_limits(key,count,started) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET count=excluded.count",
                (ai_tokens.month_key(user_id), 10**9, int(time.time())),
            )

    def free_quotes_used(self, user_id, count):
        with self.mod.db() as con:
            for index in range(count):
                con.execute("INSERT INTO events(id,user_id,name,created_at) VALUES(?,?,?,?)",
                            (f"used-{user_id}-{index}", user_id, "quote_created", int(time.time())))

    def test_assistant_creates_estimate_and_confirmation_is_idempotent(self):
        token, _ = self.account("ai-estimate-create")
        status, result = self.chat(token, tool("create_quotes", DRAFT))
        self.assertEqual(status, 200, result)
        action = result["actions"][0]
        self.assertEqual(action["tool"], "create_quotes")
        self.assertEqual(action["preview"]["kind"], "quote_draft")
        self.assertEqual(action["preview"]["total"], 630000 + 149999 + 2520000)
        self.assertEqual(self.call("/quotes", token=token)[1]["quotes"], [])  # nothing saved before confirmation

        first = self.call("/assistant/confirm", "POST", {"id": action["id"]}, token)
        self.assertEqual(first[0], 200, first)
        quote = first[1]["result"]["quote"]
        self.assertEqual(quote["ai_generated"], 1)
        self.assertEqual(quote["amount_kopecks"], action["preview"]["total"])
        again = self.call("/assistant/confirm", "POST", {"id": action["id"]}, token)
        self.assertEqual(again[1]["result"]["quote"]["id"], quote["id"])
        self.assertEqual(len(self.call("/quotes", token=token)[1]["quotes"]), 1)

    def test_invalid_model_draft_creates_no_proposal_and_failed_generation_costs_nothing(self):
        token, user_id = self.account("ai-estimate-invalid")
        replies = iter([tool("create_quotes", {**DRAFT, "items": [{**DRAFT["items"][2], "unit_price": 99}]}),
                        {"content": "Не смог составить корректную смету."}])
        status, result = self.chat(token, lambda *a, **k: next(replies))
        self.assertEqual(status, 200, result)
        self.assertEqual(result["actions"], [])
        before = self.call("/assistant", token=token)[1]["quota"]
        with patch.dict(os.environ, OPENROUTER_API_KEY="test-not-real"), patch(
            "backend.assistant.query_model", side_effect=DomainError(502, "Модель недоступна"),
        ):
            failed = self.call("/assistant/chat", "POST", {"text": "Составь смету"}, token)
        self.assertGreaterEqual(failed[0], 500)
        after = self.call("/assistant", token=token)[1]["quota"]
        # A failed generation is never charged: tokens are taken only together
        # with the committed answer.
        self.assertEqual((after["remaining"], after["monthly_used"]), (before["remaining"], before["monthly_used"]))
        self.assertEqual(len(self.call("/quotes", token=token)[1]["quotes"]), 0)

    def test_ai_estimate_after_free_allowance_but_manual_creation_stays_capped(self):
        token, user_id = self.account("ai-estimate-starter", legacy=False)
        self.free_quotes_used(user_id, 50)
        manual = self.call("/quotes", "POST", {"title": "С нуля", "client": "К", "items": [
            {"name": "Работа", "quantity": "1", "unit_price": 100}]}, token)
        self.assertEqual(manual[0], 402, manual)
        status, result = self.chat(token, tool("create_quotes", DRAFT))
        self.assertEqual(status, 200, result)
        confirmed = self.call("/assistant/confirm", "POST", {"id": result["actions"][0]["id"]}, token)
        self.assertEqual(confirmed[0], 200, confirmed)

    def test_zero_balance_blocks_only_ai_and_manual_editing_stays_free(self):
        token, user_id = self.account("ai-estimate-zero")
        status, result = self.chat(token, tool("create_quotes", DRAFT))
        quote = self.call("/assistant/confirm", "POST", {"id": result["actions"][0]["id"]}, token)[1]["result"]["quote"]
        self.exhaust(user_id)
        blocked = self.chat(token, {"content": "не должен ответить"}, "Замени ламинат на кварцвинил")
        self.assertEqual(blocked[0], 429, blocked)
        items = quote["items"] + [{"name": "Новая строка", "quantity": "2", "unit": "шт.", "unit_price": 1000, "category": "Отделка"}]
        items[0] = {**items[0], "unit_price": 50000}
        saved = self.call("/quotes/" + quote["id"] + "/autosave", "PATCH",
                          {"title": quote["title"], "client": quote["client"], "items": items, "revision": quote["revision"]}, token)
        self.assertEqual(saved[0], 200, saved)
        self.assertEqual(saved[1]["quote"]["amount_kopecks"], quote["amount_kopecks"] + 14 * 5000 + 2000)
        replay = self.call("/quotes/" + quote["id"] + "/autosave", "PATCH",
                           {"title": quote["title"], "client": quote["client"], "items": items, "revision": quote["revision"]}, token)
        self.assertTrue(replay[1].get("unchanged"), replay)  # a retried save is not applied twice
        other = [{**items[1], "unit_price": 1}] + items[2:]
        stale = self.call("/quotes/" + quote["id"] + "/autosave", "PATCH",
                          {"title": quote["title"], "client": quote["client"], "items": other, "revision": quote["revision"]}, token)
        self.assertEqual(stale[0], 409, stale)  # an old revision cannot overwrite newer edits
        self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["monthly_remaining"], 0)

    def test_risk_audit_weekly_summary_and_finance_tools_read_real_data(self):
        token, _ = self.account("ai-analysis-tools")
        quote = self.call("/quotes", "POST", {"title": "Ванная", "client": "К", "items": [
            {"name": "Укладка плитки", "quantity": "10", "unit": "м²", "unit_price": 150000, "cost_price": 200000, "category": "Отделка"},
            {"name": "Укладка плитки", "quantity": "2", "unit": "м²", "unit_price": 150000, "category": "Отделка"},
            {"name": "Затирка", "quantity": "1", "unit": "усл.", "unit_price": 0, "category": "Отделка"},
        ]}, token)[1]["quote"]
        calls = [{"id": name, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
                 for name, arguments in (("audit_quote", {"quote_id": quote["id"]}), ("weekly_summary", {}), ("finance_report", {}))]
        replies = iter([{"content": None, "tool_calls": calls}, {"content": "Готово"}])
        seen = []

        def reply(*args, **kwargs):
            seen.append(args[0] if args else kwargs.get("messages"))
            return next(replies)

        status, result = self.chat(token, reply, "Проверь смету и дай сводку недели")
        self.assertEqual(status, 200, result)
        audit, weekly, finance = [json.loads(m["content"]) for m in seen[-1] if isinstance(m, dict) and m.get("role") == "tool"]
        issues = " ".join(item["issue"] for item in audit["findings"])
        self.assertIn("нет цены", issues)
        self.assertIn("повторяет строку 1", issues)
        self.assertIn("в убыток", issues)
        self.assertIn("демонтаж", audit["possibly_missing_stages"])
        self.assertEqual(weekly["quotes_created"], 1)
        self.assertIn("orders", finance)

    def test_app_actions_are_buttons_checked_on_the_server(self):
        token, _ = self.account("ai-app-actions")
        other, _ = self.account("ai-app-actions-other")
        foreign = self.call("/quotes", "POST", {"title": "Чужая", "client": "К", "items": [
            {"name": "Работа", "quantity": "1", "unit_price": 100}]}, other)[1]["quote"]
        replies = iter([
            {"content": None, "tool_calls": [
                {"id": "a", "type": "function", "function": {"name": "suggest_app_action", "arguments": json.dumps({"action": "connect_cloud_drive", "provider": "yandex_disk"})}},
                {"id": "b", "type": "function", "function": {"name": "suggest_app_action", "arguments": json.dumps({"action": "open_quote", "quote_id": foreign["id"]})}},
                {"id": "c", "type": "function", "function": {"name": "material_calculator", "arguments": json.dumps({"kind": "laminate", "values": {"length": "5", "width": "4", "pack": "2.2"}})}},
                {"id": "d", "type": "function", "function": {"name": "suggest_app_action", "arguments": json.dumps({"action": "run_sql"})}},
            ]},
            {"content": "Нужно 10 упаковок. Подключите диск кнопкой ниже."},
        ])
        seen = []

        def reply(*args, **kwargs):
            seen.append(args[0] if args else kwargs.get("messages"))
            return next(replies)

        status, result = self.chat(token, reply, "Подключи яндекс диск и посчитай ламинат")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["client_actions"], [{"action": "connect_cloud_drive", "provider": "yandex_disk", "label": "Подключить Яндекс Диск"}])
        tool_results = [json.loads(m["content"]) for m in seen[-1] if isinstance(m, dict) and m.get("role") == "tool"]
        self.assertIn("error", tool_results[1])  # another workspace's estimate is never offered
        self.assertEqual(tool_results[2]["packages"]["value"], "10")
        self.assertIn("error", tool_results[3])


if __name__ == "__main__":
    unittest.main()
