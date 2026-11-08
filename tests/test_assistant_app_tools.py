"""Regression tests for assistant quote audits on legacy and optional lines."""
import unittest

from backend.assistant_app_tools import audit_quote


class QuoteAuditTests(unittest.TestCase):
    def test_zero_or_invalid_quantity_is_flagged_and_optional_lines_are_ignored(self):
        quote = {
            "id": "quote-1",
            "title": "Ремонт ванной",
            "description": "",
            "amount_kopecks": 50000,
            "items": [
                {"name": "Основная работа", "quantity": "0", "unit": "м²",
                 "unit_price": 50000, "category": "Работы", "included": True},
                {"name": "Старая позиция", "quantity": "ошибка", "unit": "шт.",
                 "unit_price": 20000, "category": "Работы", "included": True},
                {"name": "Опционально", "quantity": "0", "unit": "шт.",
                 "unit_price": 500000, "category": "Материалы", "included": False},
            ],
        }

        class Catalog:
            def execute(self, sql, params):
                self_sql = sql  # The audit must only access the current workspace's catalog.
                if "workspace_id=?" not in self_sql or params != ("workspace-1",):
                    raise AssertionError("Catalog query not workspace-scoped")
                return [{"name": "Опционально", "unit": "шт.", "price": 10000}]

        class Service:
            wid = "workspace-1"
            con = Catalog()

            def get(self, kind, record_id):
                if kind != "quotes" or record_id != "quote-1":
                    raise AssertionError("Unexpected record access")
                return {"id": record_id}

            def quote_view(self, record):
                return quote

            def finance_visible(self):
                return False

        findings = audit_quote(Service(), "quote-1")["findings"]
        quantity_issues = [row for row in findings if "нулевое или некорректное количество" in row["issue"]]
        self.assertEqual([row["row"] for row in quantity_issues], [1, 2])
        self.assertFalse(any(row["row"] == 3 for row in findings))

    def test_positive_quantity_does_not_trigger_quantity_warning(self):
        from unittest.mock import MagicMock
        service = MagicMock()
        service.wid = "workspace-1"
        service.get.return_value = {"id": "q"}
        service.quote_view.return_value = {
            "id": "q", "title": "Укладка плитки", "description": "",
            "amount_kopecks": 20000,
            "items": [{"name": "Плитка", "quantity": "1.25", "unit": "м²",
                       "unit_price": 16000, "category": "Работы", "included": True}],
        }
        service.con.execute.return_value = []
        service.finance_visible.return_value = False
        findings = audit_quote(service, "q")["findings"]
        self.assertFalse(any("количество" in row["issue"] for row in findings))


if __name__ == "__main__":
    unittest.main()
