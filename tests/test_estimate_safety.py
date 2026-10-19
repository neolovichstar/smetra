"""Regression checks for mathematically authoritative estimate drafting."""
import inspect
import unittest

from backend import ai
from backend.business import (
    DomainError,
    TERMS_VERSION,
    calculate,
    has_legal_acceptance,
    require_legal_acceptance,
)


class EstimateSafetyTests(unittest.TestCase):
    def test_line_math_is_exact_and_server_owned(self):
        items, total, cost = calculate([
            {
                "name": "Грунтовка",
                "quantity": "2.5",
                "unit": "м²",
                "unit_price": 10000,
                "discount": "10",
                "tax": "20",
            }
        ])
        self.assertEqual(items[0]["subtotal"], 27000)
        self.assertEqual(items[0]["tax_amount"], 4500)
        self.assertEqual(total, 27000)
        self.assertEqual(cost, 0)

    def test_current_versioned_consent_is_required(self):
        self.assertTrue(has_legal_acceptance({
            "terms_accepted_at": 1,
            "terms_version": TERMS_VERSION,
        }))
        self.assertFalse(has_legal_acceptance({
            "terms_accepted_at": 1,
            "terms_version": "outdated",
        }))
        with self.assertRaises(DomainError) as ctx:
            require_legal_acceptance({
                "terms_accepted_at": None,
                "terms_version": None,
            })
        self.assertEqual(ctx.exception.status, 428)

    def test_prompt_only_structures_line_items_and_requests_site_measurements(self):
        source = inspect.getsource(ai._draft)
        self.assertIn('"response_format"', source)
        self.assertIn('"json_schema"', source)
        self.assertIn('"strict": True', source)
        self.assertIn("черновой ассистент-структуризатор", source)
        self.assertIn("КАТЕГОРИЧЕСКИ НЕ ВЫЧИСЛЯЙ", source)
        self.assertIn("Требует замера по месту", source)
        self.assertIn("unit_price=0", source)

    def test_narrative_aggregate_totals_are_rejected(self):
        self.assertTrue(ai._contains_aggregate_total({
            "title": "Ремонт",
            "description": "Общая стоимость: 150000 ₽",
            "terms": "",
            "items": [{"name": "Грунтовка", "description": "Требует замера по месту"}],
        }))
        self.assertFalse(ai._contains_aggregate_total({
            "title": "Ремонт ванной",
            "description": "Предварительный список работ",
            "terms": "Цены проверить по региону",
            "items": [{"name": "Грунтовка", "description": "Требует замера по месту"}],
        }))


if __name__ == "__main__":
    unittest.main()
