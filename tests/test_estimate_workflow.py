"""Commercial calculations, protected alternatives and evidence-based own rates."""
import concurrent.futures
from types import SimpleNamespace
import unittest
import uuid

from backend.assistant import model_tools, prepare
from backend.business import Service
from tests import test_business


class WorkflowTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def setUp(self):
        self.mod.RATE.clear()
        self.owner, self.uid = self.account("workflow-"+uuid.uuid4().hex[:8])
        with self.mod.db() as con:
            con.execute("UPDATE users SET entitlement_until=? WHERE id=?", (self.mod.now()+86400, self.uid))
        code, result = self.call("/quotes", "POST", {"title": "Заказ", "client": "Иванов", "items": [
            {"name": "Работы", "quantity": "1", "unit": "м²", "unit_price": 12000000, "cost_price": 10000000}]}, self.owner)
        self.assertEqual(code, 201, result)
        self.quote = result["quote"]
        code, result = self.call("/projects", "POST", {"name": "Заказ", "amount_kopecks": 12000000, "internal_cost": 10000000}, self.owner)
        self.assertEqual(code, 201, result)
        self.project = result["item"]

    def proposal(self, name, args):
        with self.mod.db() as con:
            service = Service(SimpleNamespace(headers={}), con, self.base)
            service.user = con.execute("SELECT * FROM users WHERE id=?", (self.uid,)).fetchone()
            service.wid = con.execute("SELECT workspace_id FROM workspace_members WHERE user_id=?", (self.uid,)).fetchone()[0]
            service.role = "owner"
            return prepare(service, name, args)

    def test_forecast_commitments_are_included_once_and_expenses_make_it_stale(self):
        endpoint = "/estimate-workflow/forecast/"+self.project["id"]
        self.assertEqual(self.call("/expenses", "POST", {"project_id": self.project["id"], "amount_kopecks": 1000000, "category": "Материалы"}, self.owner, key=uuid.uuid4().hex)[0], 201)
        code, result = self.call(endpoint, "PATCH", {"revision": self.project["revision"], "remaining_cost": 4000000, "committed_cost": 3000000}, self.owner)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["finance"]["estimate_at_completion"], 5000000)
        self.assertEqual(result["finance"]["forecast_profit"], 7000000)
        self.assertFalse(result["finance"]["forecast_stale"])
        self.assertEqual(self.call("/expenses", "POST", {"project_id": self.project["id"], "amount_kopecks": 100000, "category": "Доставка"}, self.owner, key=uuid.uuid4().hex)[0], 201)
        updated = self.call(endpoint, token=self.owner)[1]
        self.assertTrue(updated["finance"]["forecast_stale"])
        self.assertIsNone(updated["finance"]["forecast_profit"])
        self.assertEqual(self.call(endpoint, "PATCH", {"revision": result["revision"], "remaining_cost": 1, "committed_cost": 2}, self.owner)[0], 400)
        self.assertEqual(self.call(endpoint, "PATCH", {"revision": self.project["revision"], "remaining_cost": 1}, self.owner)[0], 409)

    def test_discount_reduces_profit_and_publication_requires_low_margin_confirmation(self):
        endpoint = "/estimate-workflow/discount/"+self.quote["id"]
        code, result = self.call(endpoint, "POST", {"revision": self.quote["revision"], "percent": "10"}, self.owner)
        self.assertEqual(code, 200, result)
        self.assertEqual((result["before"]["profit"], result["after"]["profit"]), (2000000, 800000))
        self.assertEqual(result["after"]["internal_cost"], 10000000)
        self.call("/estimate-workflow/margin-policy", "PATCH", {"minimum_margin_pct": "10"}, self.owner)
        values = {"revision": self.quote["revision"], "percent": "10", "confirmation": True}
        self.assertEqual(self.call(endpoint+"/apply", "POST", values, self.owner)[0], 409)
        code, result = self.call(endpoint+"/apply", "POST", {**values, "low_margin_confirmed": True}, self.owner)
        self.assertEqual(code, 200, result)
        body = {"revision": result["quote"]["revision"], "review_confirmed": True}
        self.assertEqual(self.call("/quotes/"+self.quote["id"]+"/publish", "POST", body, self.owner)[0], 409)
        self.assertEqual(self.call("/quotes/"+self.quote["id"]+"/publish", "POST", {**body, "low_margin_confirmed": True}, self.owner)[0], 200)

    def test_forecast_and_discount_assistant_do_nothing_before_confirmation(self):
        action = self.proposal("update_order_forecast", {"id": self.project["id"], "remaining_cost": 1000000, "committed_cost": 200000})
        self.assertEqual(self.call("/estimate-workflow/forecast/"+self.project["id"], token=self.owner)[1]["cost_forecast"], {})
        code, applied = self.call("/assistant/confirm", "POST", {"id": action["id"]}, self.owner)
        self.assertEqual(code, 200, applied)
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, self.owner)[1], applied)
        action = self.proposal("apply_estimate_discount", {"id": self.quote["id"], "percent": "10"})
        self.assertEqual(self.call("/quotes/"+self.quote["id"], token=self.owner)[1]["quote"]["amount_kopecks"], 12000000)
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, self.owner)[0], 200)

    def test_assistant_alternatives_reuse_server_rows_and_preserve_private_costs(self):
        action = self.proposal("create_estimate_alternatives", {"id": self.quote["id"], "variants": [{"label": "Со скидкой", "rows": [1], "discount_percent": "5"}]})
        self.assertEqual(self.call("/estimate-workflow/alternatives/"+self.quote["id"], token=self.owner)[1]["quotes"][0]["alternative_root_id"], None)
        code, result = self.call("/assistant/confirm", "POST", {"id": action["id"]}, self.owner)
        self.assertEqual(code, 200, result)
        variant = result["result"]["quotes"][1]
        self.assertEqual(variant["items"][0]["cost_price"], 10000000)
        self.assertTrue(variant["ai_generated"])

    def test_model_gets_relevant_commercial_tools_without_loading_every_schema(self):
        plain = {tool["function"]["name"] for tool in model_tools([{"role": "user", "content": "Привет"}])}
        discount = {tool["function"]["name"] for tool in model_tools([{"role": "user", "content": "Дай скидку 10 процентов"}])}
        self.assertNotIn("apply_estimate_discount", plain)
        self.assertIn("apply_estimate_discount", discount)
        discovered = model_tools([{"role": "assistant", "tool_calls": [{"function": {"name": "list_estimate_assemblies"}}]}])
        self.assertIn("apply_estimate_assembly", {tool["function"]["name"] for tool in discovered})

    def alternatives(self):
        row = self.quote["items"][0]
        variants = [{"label": "Вариант А", "items": [{**row, "quantity": "2"}]}, {"label": "Вариант Б", "items": [{**row, "quantity": "3"}]}]
        code, result = self.call("/estimate-workflow/alternatives/"+self.quote["id"]+"/apply", "POST", {"revision": self.quote["revision"], "variants": variants, "confirmation": True}, self.owner)
        self.assertEqual(code, 201, result)
        return result["quotes"]

    def test_alternative_acceptance_is_mutually_exclusive_under_concurrency(self):
        quotes = self.alternatives()
        label = "recipient-"+uuid.uuid4().hex[:8]
        recipient, recipient_id = self.account(label)
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=? WHERE id=?", (self.mod.now(), recipient_id))
        decisions = []
        for quote in quotes:
            self.assertTrue(quote["protection_enabled"])
            code, result = self.call("/quotes/"+quote["id"]+"/publish", "POST", {"revision": quote["revision"], "review_confirmed": True}, self.owner)
            self.assertEqual(code, 200, result)
            code, link = self.call("/protected-links", "POST", {"quote_id": quote["id"], "recipient_email": label+"@test.invalid"}, self.owner)
            self.assertEqual(code, 201, link)
            token = link["url"].split("#")[1]
            code, opened = self.call("/public/protected/open", "POST", {"token": token})
            self.assertEqual(code, 200, opened)
            decisions.append({"token": token, "view_token": opened["view_token"], "action": "approved", "confirmation": True,
                              "permissions_revision": opened["document"]["permissions_revision"], "snapshot_sha256": opened["document"]["snapshot_sha256"]})
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda payload: self.call("/public/protected/respond", "POST", payload, recipient)[0], decisions[:2]))
        self.assertEqual(sorted(results), [200, 409])
        statuses = [self.call("/quotes/"+quote["id"], token=self.owner)[1]["quote"]["approval_state"] for quote in quotes]
        self.assertEqual(statuses.count("approved"), 1)
        self.assertEqual(statuses.count("rejected"), 2)

    def test_own_rates_require_completed_job_and_explicit_approval(self):
        code, obj = self.call("/construction/objects", "POST", {"name": "Завершённый объект"}, self.owner)
        self.assertEqual(code, 201, obj)
        obj = obj["object"]
        with self.mod.db() as con:
            con.execute("UPDATE construction_objects SET project_id=? WHERE id=?", (self.project["id"], obj["id"]))
        path = "/construction/objects/"+obj["id"]
        code, material = self.call(path+"/quantities", "POST", {"kind": "material", "title": "Клей", "formula": "10", "unit": "кг", "unit_price": 10000}, self.owner)
        self.assertEqual(code, 201, material)
        material = material["quantity"]
        for quantity, price in (("2", 10000), ("3", 20000)):
            self.assertEqual(self.call(path+"/purchases", "POST", {"material_id": material["id"], "purchased_on": "2026-11-01", "quantity": quantity,
                                  "unit_price_kopecks": price, "status": "received"}, self.owner)[0], 201)
        rates = "/estimate-workflow/rates/"+obj["id"]
        self.assertEqual(self.call(rates, token=self.owner)[0], 409)
        self.call("/projects/"+self.project["id"], "PATCH", {"revision": self.project["revision"], "status": "completed"}, self.owner)
        code, result = self.call(rates, token=self.owner)
        self.assertEqual(code, 200, result)
        candidate = result["items"][0]
        self.assertEqual(candidate["cost_price"], 16000)
        endpoint = "/estimate-workflow/learn-rate/"+material["id"]
        body = {"source_sha256": candidate["source_sha256"], "create": True}
        self.assertEqual(self.call(endpoint, "POST", body, self.owner)[0], 400)
        code, result = self.call(endpoint, "POST", {**body, "confirmation": True}, self.owner)
        self.assertEqual(code, 201, result)
        self.assertEqual((result["item"]["cost_price"], result["item"]["price"]), (16000, 0))
        self.assertEqual(self.call(endpoint, "POST", {**body, "confirmation": True}, self.owner)[1]["item"]["id"], result["item"]["id"])
        self.assertEqual(self.call(endpoint, "POST", {**body, "confirmation": True, "source_sha256": "stale"}, self.owner)[0], 409)

    def test_all_workflow_records_are_isolated_between_companies(self):
        other, _ = self.account("other-workflow-"+uuid.uuid4().hex[:8])
        for method, path, data in (("GET", "forecast/"+self.project["id"], None), ("GET", "economics/"+self.quote["id"], None),
                                  ("POST", "discount/"+self.quote["id"], {"revision": self.quote["revision"], "percent": "10"}),
                                  ("GET", "alternatives/"+self.quote["id"], None)):
            self.assertEqual(self.call("/estimate-workflow/"+path, method, data, other)[0], 404)


if __name__ == "__main__":
    unittest.main()
