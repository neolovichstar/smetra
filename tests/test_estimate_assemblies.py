"""Deterministic assembly calculations, tenant isolation and immutable offers."""
import io
import json
import unittest
import uuid
from types import SimpleNamespace

from backend.business import DomainError, Service, calculate
from backend.estimate_assemblies import normalize, recalculate, scope
from tests import test_business


def definition():
    return {"title": "Облицовка", "currency": "RUB", "parameters": {"area": "10", "rate": "0.3", "waste": "10"},
            "labels": {"area": "Площадь, м²", "rate": "Расход, кг/м²", "waste": "Запас, %"},
            "items": [
                {"name": "Укладка", "unit": "м²", "kind": "work", "expression": "area", "unit_price": 10000, "cost_price": 3000},
                {"name": "Клей", "unit": "кг", "kind": "material", "expression": "area*rate*(1+waste/100)", "unit_price": 20000, "cost_price": 7000}],
            "scope": {"included": ["Укладка и клей"], "excluded": ["Вывоз мусора"], "customer": ["Плитка заказчика"]}}


class AssemblyMathTests(unittest.TestCase):
    def test_decimal_exactness_and_no_automatic_norms(self):
        data = normalize(definition())
        self.assertEqual(data["items"][1]["quantity"], "3.3000")
        self.assertEqual(data["items"][1]["subtotal"], 66000)
        self.assertEqual(data["parameters"]["rate"], "0.3")

    def test_untrusted_expressions_and_parameters_are_rejected(self):
        for expression in ("__import__('os')", "area**100000", "area/0", "unknown", "-area"):
            data = definition()
            data["items"][0]["expression"] = expression
            with self.subTest(expression=expression), self.assertRaises(DomainError):
                normalize(data)
        for value in (True, "NaN", "-1", "1000001"):
            data = definition()
            data["parameters"]["area"] = value
            with self.subTest(value=value), self.assertRaises(DomainError):
                normalize(data)

    def test_scope_rejects_hidden_fields_and_oversized_notes(self):
        for data in ({"cost_price": 123}, {"excluded": "no"}, {"included": ["x"*501]}, {"included": ["x"]*21}):
            with self.subTest(data=data), self.assertRaises(DomainError):
                scope(data)


class AssemblyFlows(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def setUp(self):
        self.mod.RATE.clear()
        self.owner, self.owner_id = self.account("assembly-" + uuid.uuid4().hex[:10])
        code, result = self.call("/assemblies", "POST", definition(), self.owner)
        self.assertEqual(code, 201, result)
        self.assembly = result["assembly"]

    def preview(self, **extra):
        code, result = self.call("/assemblies/preview", "POST", {"id": self.assembly["id"],
            "parameters": {"area": "20", "rate": "0.3", "waste": "10"}, **extra}, self.owner)
        self.assertEqual(code, 200, result)
        return result

    def quote(self):
        draft = self.preview()
        code, result = self.call("/quotes", "POST", {"title": "Квартира", "client": "Иванов", "items": draft["items"], "scope": draft["scope"]}, self.owner)
        self.assertEqual(code, 201, result)
        return result["quote"]

    def test_assembly_isolated_from_templates_and_other_tenants(self):
        outsider, _ = self.account("assembly-other-" + uuid.uuid4().hex[:8])
        for method, path, data in (("GET", "/assemblies/"+self.assembly["id"], None),
                ("POST", "/assemblies/preview", {"id": self.assembly["id"]}),
                ("PATCH", "/assemblies/"+self.assembly["id"], {**definition(), "revision": 1}),
                ("DELETE", "/assemblies/"+self.assembly["id"], {})):
            self.assertEqual(self.call(path, method, data, outsider)[0], 404)
        self.assertEqual(self.call("/assemblies", token=outsider)[1]["items"], [])
        self.assertEqual(self.call("/templates", token=self.owner)[1]["items"], [])
        self.assertEqual(self.call("/templates/"+self.assembly["id"], token=self.owner)[0], 404)
        self.assertEqual(self.call("/templates/"+self.assembly["id"], "POST", {}, self.owner)[0], 404)

    def test_recalculate_preserves_manual_rows_rates_and_identity(self):
        quote = self.quote()
        manual = calculate([{"name": "Ручная строка", "unit_price": 10001}])[0][0]
        before = quote["items"] + [manual]
        result = recalculate({"items": before, "instance_id": before[0]["assembly"]["instance_id"],
                              "parameters": {"area": "30", "rate": "0.3", "waste": "10"}})
        self.assertEqual(result["items"][-1], manual)
        self.assertEqual(result["items"][0]["line_id"], before[0]["line_id"])
        self.assertEqual(result["items"][1]["quantity"], "9.9000")
        self.assertEqual(result["items"][1]["cost_price"], 7000)
        code, saved = self.call("/quotes/"+quote["id"], "PATCH", {"revision": quote["revision"], "items": result["items"]}, self.owner)
        self.assertEqual(code, 200, saved)
        self.assertEqual(saved["quote"]["items"], result["items"])
        result["items"][0]["quantity"] = "99"
        self.assertEqual(self.call("/quotes/"+quote["id"], "PATCH", {"revision": saved["quote"]["revision"], "items": result["items"]}, self.owner)[0], 409)

    def test_definition_revision_currency_and_parameters_are_checked(self):
        for data in ({"revision": True}, {"revision": 2}, {"currency": "USD"}, {"parameters": {"area": "20"}}):
            self.assertIn(self.call("/assemblies/preview", "POST", {"id": self.assembly["id"], **data}, self.owner)[0], (400, 409))
        code, result = self.call("/assemblies/"+self.assembly["id"], "PATCH", {**definition(), "revision": 1}, self.owner)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["assembly"]["revision"], 2)
        self.assertEqual(self.call("/assemblies/"+self.assembly["id"], "PATCH", {**definition(), "revision": 1}, self.owner)[0], 409)

    def test_protected_projection_and_exports_freeze_scope_and_hide_formulas(self):
        quote = self.quote()
        code, result = self.call("/quotes/"+quote["id"]+"/publish", "POST", {"revision": quote["revision"], "review_confirmed": True}, self.owner)
        self.assertEqual(code, 200, result)
        quote = result["quote"]
        code, result = self.call("/protected-links", "POST", {"quote_id": quote["id"], "settings": {"allow_pdf": True, "allow_excel": True}}, self.owner)
        self.assertEqual(code, 201, result)
        token = result["url"].split("#")[1]
        code, opened = self.call("/public/protected/open", "POST", {"token": token})
        self.assertEqual(code, 200, opened)
        document = opened["document"]
        self.assertEqual(document["scope"]["customer"], ["Плитка заказчика"])
        for hidden in ('"assembly":', '"expression":', '"parameters":', '"cost_price":', '"template_id":'):
            self.assertNotIn(hidden, json.dumps(document, ensure_ascii=False))
        self.assertEqual(self.call("/quotes/"+quote["id"], "PATCH", {"revision": quote["revision"], "scope": {"customer": ["Новое условие"]}}, self.owner)[0], 200)
        payload = {"token": token, "view_token": opened["view_token"]}
        self.assertEqual(self.call("/public/protected/view", "POST", payload)[1]["document"]["scope"], document["scope"])
        for kind in ("pdf", "xlsx"):
            code, content = self.call("/public/protected/"+kind, "POST", payload, raw=True)
            self.assertEqual(code, 200)
            if kind == "pdf":
                from pypdf import PdfReader
                text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
            else:
                from openpyxl import load_workbook
                text = str(list(load_workbook(io.BytesIO(content)).active.values))
            self.assertIn("Плитка заказчика", text)
            self.assertNotIn("Новое условие", text)
            self.assertNotIn("area*rate", text)

    def test_copy_and_template_keep_assembly_snapshot_after_definition_deleted(self):
        quote = self.quote()
        self.assertEqual(self.call("/assemblies/"+self.assembly["id"], "DELETE", {}, self.owner)[0], 200)
        code, result = self.call("/quotes/"+quote["id"]+"/copy", "POST", {}, self.owner)
        self.assertEqual(code, 201, result)
        self.assertEqual(result["quote"]["scope"], quote["scope"])
        self.assertEqual(result["quote"]["items"][0]["assembly"], quote["items"][0]["assembly"])
        self.assertEqual(self.call("/quotes/"+quote["id"]+"/template", "POST", {}, self.owner)[0], 201)

    def proposal(self, name, args):
        from backend.assistant import prepare
        with self.mod.db() as con:
            service = Service(SimpleNamespace(), con, self.base)
            service.user = dict(con.execute("SELECT * FROM users WHERE id=?", (self.owner_id,)).fetchone())
            service.wid = con.execute("SELECT workspace_id FROM workspace_members WHERE user_id=?", (self.owner_id,)).fetchone()[0]
            service.role = "owner"
            return prepare(service, name, args)

    def test_assistant_requires_confirmation_is_idempotent_and_rejects_stale_quotes(self):
        quote = self.quote()
        action = self.proposal("apply_estimate_assembly", {"quote_id": quote["id"], "id": self.assembly["id"],
                                "parameters": self.assembly["parameters"]})
        self.assertEqual(len(self.call("/quotes/"+quote["id"], token=self.owner)[1]["quote"]["items"]), 2)
        self.assertTrue(action["preview"]["rows"])
        code, result = self.call("/assistant/confirm", "POST", {"id": action["id"]}, self.owner)
        self.assertEqual(code, 200, result)
        self.assertEqual(len(result["result"]["quote"]["items"]), 4)
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, self.owner)[1], result)
        action = self.proposal("set_estimate_scope", {"quote_id": quote["id"], "scope": {"excluded": ["Новая доставка"]}})
        current = self.call("/quotes/"+quote["id"], token=self.owner)[1]["quote"]
        self.call("/quotes/"+quote["id"], "PATCH", {"revision": current["revision"], "terms": "Изменено"}, self.owner)
        self.assertEqual(self.call("/assistant/confirm", "POST", {"id": action["id"]}, self.owner)[0], 409)

    def test_group_parameters_cannot_be_partially_modified(self):
        rows = self.preview()["items"]
        rows[1]["assembly"]["parameters"]["area"] = "30"
        rows[1]["quantity"] = "9.9000"
        with self.assertRaises(DomainError):
            calculate(rows)

    def test_member_cannot_read_private_formulas_or_change_bound_quantities(self):
        quote = self.quote()
        member, member_id = self.account("assembly-member-"+uuid.uuid4().hex[:8])
        with self.mod.db() as con:
            wid = con.execute("SELECT workspace_id FROM workspace_members WHERE user_id=? AND role='owner'", (self.owner_id,)).fetchone()[0]
            con.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(?,?,'member')", (wid, member_id))
        public = self.call("/quotes/"+quote["id"], token=member, workspace=wid)[1]["quote"]
        self.assertNotIn("assembly", public["items"][0])
        self.assertNotIn("cost_price", public["items"][0])
        self.assertTrue(public["items"][0]["quantity_locked"])
        public["items"][0]["quantity"] = "999"
        self.assertEqual(self.call("/quotes/"+quote["id"], "PATCH", {"revision": quote["revision"], "items": public["items"]}, member, workspace=wid)[0], 409)
        public["items"][0]["quantity"] = quote["items"][0]["quantity"]
        self.assertEqual(self.call("/quotes/"+quote["id"], "PATCH", {"revision": quote["revision"], "items": public["items"], "terms": "Новые условия"}, member, workspace=wid)[0], 200)
        saved = self.call("/quotes/"+quote["id"], token=self.owner)[1]["quote"]
        self.assertEqual(saved["items"][0]["assembly"], quote["items"][0]["assembly"])
        self.assertEqual(saved["items"][0]["cost_price"], quote["items"][0]["cost_price"])


if __name__ == "__main__":
    unittest.main()
