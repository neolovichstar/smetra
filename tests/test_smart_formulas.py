"""Deterministic, safe calculation rules used by the assistant."""
import json
import sqlite3
import unittest
from unittest.mock import patch

from backend.business import DomainError
from backend.smart_formulas import PREFIX, calculate, evaluate, list_rules, save_rule


class FormulaTests(unittest.TestCase):
    def test_conditional_waste_and_decimal_exactness(self):
        self.assertEqual(
            calculate("area * (1.15 if complex > 0 else 1.10)",
                      {"area": "120", "complex": "0"})["result"], "132"
        )
        self.assertEqual(
            calculate("area * (1.15 if complex > 0 else 1.10)",
                      {"area": "120", "complex": "1"})["result"], "138"
        )
        self.assertEqual(calculate("0.1+0.2")["result"], "0.3")
        self.assertEqual(calculate("wall * rate * coats * (1+waste/100)",
                                   {"wall": "120", "rate": "0.18", "coats": "2",
                                    "waste": "10"})["result"], "47.52")

    def test_formula_never_runs_arbitrary_python(self):
        dangerous = (
            "__import__('os').system('whoami')",
            "(1).__class__",
            "sum([1,2,3])",
            "value[0]",
            "2**1000000",
            "2//3",
            "True",
            "[x for x in y]",
        )
        for expr in dangerous:
            with self.subTest(expression=expr):
                with self.assertRaises(DomainError):
                    calculate(expr, {"value": "2", "x": "1", "y": "2"})

    def test_rejects_invalid_inputs(self):
        for expr, values in (
            ("10/0", {}),
            ("amount+1", {}),
            ("amount+1", {"amount": "NaN"}),
            ("amount+1", {"amount": "1e999"}),
            ("amount+1", {"amount": "1000000000001"}),
            ("amount+1", {"amount": True}),
            ("amount+1", {"amount": "2", "unused": "3"}),
            ("(1+2)*5", {}),
        ):
            if expr == "(1+2)*5":
                self.assertEqual(calculate(expr)["result"], "15")
                continue
            with self.subTest(expression=expr, values=values):
                with self.assertRaises(DomainError):
                    calculate(expr, values)

    def test_rejects_excessive_nesting(self):
        with self.assertRaises(DomainError):
            calculate("+"*20 + "1")


class RuleStoreTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(
            "CREATE TABLE workspace_knowledge("
            "id TEXT PRIMARY KEY,workspace_id TEXT,title TEXT,content TEXT,"
            "kind TEXT,enabled INTEGER,created_by TEXT,created_at INTEGER,updated_at INTEGER)"
        )

        class Service:
            pass
        self.service = Service()
        self.service.con = self.con
        self.service.wid = "one"
        self.service.user = {"id": "author"}
        self.service.write_access = lambda managerial=False: self.assertTrue(managerial)
        self.granted = patch("backend.entitlements.workspace_feature_access",
                             return_value={"allowed": True})
        self.granted.start()
        self.addCleanup(self.granted.stop)
        self.addCleanup(self.con.close)

    def test_save_update_list_and_apply_by_id(self):
        a = save_rule(self.service, {"title": "Запас на плитку",
                                     "expression": "area*(1+waste/100)", "unit": "м²",
                                     "defaults": {"waste": "10"}})
        self.assertTrue(a["saved"])
        stored = self.con.execute("SELECT * FROM workspace_knowledge").fetchone()
        self.assertEqual(stored["workspace_id"], "one")
        self.assertTrue(stored["content"].startswith(PREFIX))
        self.assertEqual(json.loads(stored["content"][len(PREFIX):])["defaults"], {"waste": "10"})
        self.assertEqual(evaluate(self.service, {"rule_id": a["id"], "values": {"area": "30"}})["result"], "33")
        self.assertEqual(len(list_rules(self.service)["rules"]), 1)
        updated = save_rule(self.service, {"title": "Запас на плитку",
                                            "expression": "area*(1+waste/100)",
                                            "defaults": {"waste": "15"}})
        self.assertEqual(a["id"], updated["id"])
        self.assertEqual(evaluate(self.service, {"rule_id": a["id"], "values": {"area": "20"}})["result"], "23")

    def test_workspace_isolation_and_entitlement(self):
        other = save_rule(self.service, {"title": "Запас", "expression": "area*1.1"})
        self.service.wid = "two"
        self.assertEqual(list_rules(self.service)["rules"], [])
        with self.assertRaises(DomainError):
            evaluate(self.service, {"rule_id": other["id"], "values": {"area": "50"}})
        with patch("backend.entitlements.workspace_feature_access", return_value={"allowed": False}):
            with self.assertRaises(DomainError) as err:
                evaluate(self.service, {"expression": "1+1"})
            self.assertEqual(err.exception.code, 402) if hasattr(err.exception, "code") else None
            with self.assertRaises(DomainError):
                save_rule(self.service, {"title": "Нельзя", "expression": "1+1"})

    def test_existing_nonformula_knowledge_is_preserved(self):
        self.con.execute(
            "INSERT INTO workspace_knowledge VALUES(?,?,?,?,?,?,?,?,?)",
            ("old", "one", "Строительные нормы", "Не перезаписывать", "rule", 1, "author", 1, 1),
        )
        self.con.commit()
        with self.assertRaises(DomainError):
            save_rule(self.service, {"title": "Строительные нормы", "expression": "2*2"})
        self.assertEqual(self.con.execute("SELECT content FROM workspace_knowledge WHERE id='old'").fetchone()[0],
                         "Не перезаписывать")


if __name__ == "__main__":
    unittest.main()
