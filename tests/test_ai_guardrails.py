"""Offline regression tests for the AI estimate safety boundary."""
import unittest

from backend.ai import _contains_financial_total, _validate_draft_item
from backend.business import DomainError, calculate


def item(**overrides):
    value = {
        "name": "Покраска стен",
        "description": "Работа по подготовке и покраске.",
        "quantity": "2",
        "unit": "м²",
        "unit_price": 15000,
    }
    value.update(overrides)
    return value


class AIEstimateGuardrailTests(unittest.TestCase):
    def test_final_money_claims_are_rejected_in_free_text(self):
        for phrase in (
            "Итого ремонт обойдётся в 150 000 руб.",
            "Стоимость работ составит 120000 ₽",
            "Материалы — 500 рублей",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(_contains_financial_total(phrase))
                with self.assertRaises(ValueError):
                    _validate_draft_item(item(description=phrase))

    def test_nonfinancial_description_is_allowed(self):
        self.assertFalse(_contains_financial_total("Подготовить стены под покраску"))
        self.assertEqual(_validate_draft_item(item())["unit_price"], 15000)

    def test_hidden_preparatory_work_always_requires_site_measurement(self):
        result = _validate_draft_item(item(name="Грунтовка стен", description="Нанести грунт"))
        self.assertIn("Требует замера по месту", result["description"])
        already_marked = _validate_draft_item(
            item(name="Демонтаж плитки", description="Требует замера по месту")
        )
        self.assertEqual(already_marked["description"].count("Требует замера по месту"), 1)

    def test_unknown_price_stays_zero_and_is_not_calculated_by_ai(self):
        result = _validate_draft_item(item(unit_price=0))
        self.assertEqual(result["unit_price"], 0)

    def test_malformed_structured_fields_are_rejected(self):
        invalid = (
            item(quantity=2),
            item(unit=None),
            item(name=" "),
            item(unit_price=True),
            item(unit_price=-1),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                with self.assertRaises((ValueError, DomainError)):
                    _validate_draft_item(candidate)

    def test_backend_calculates_line_totals_deterministically(self):
        lines, total, cost = calculate([
            {
                "name": "Покраска стен",
                "quantity": "2",
                "unit": "м²",
                "unit_price": 15000,
                "tax": "20",
            }
        ])
        self.assertEqual(lines[0]["subtotal"], 36000)
        self.assertEqual(total, 36000)
        self.assertEqual(cost, 0)


if __name__ == "__main__":
    unittest.main()
