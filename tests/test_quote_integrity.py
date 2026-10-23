"""Published estimate financial integrity and fingerprint contract."""
import copy
import re
import unittest

from backend.business import calculate
from backend.quote_integrity import InvalidSnapshot, fingerprint, verify_totals


class QuoteIntegrityTests(unittest.TestCase):
    def snapshot(self):
        items = [
            {"name": "Шпаклёвка", "quantity": "3.375", "unit": "м2",
             "unit_price": 23521, "cost_price": 12100,
             "tax": "20", "discount": "4.5", "coefficient": "1.15"},
            {"name": "Теплый пол", "quantity": "2", "unit": "м2",
             "unit_price": 74000, "optional": True, "included": False},
        ]
        rows, total, internal = calculate(items)
        return {"title": "Отделка", "currency": "RUB", "itemized": 1,
                "items": rows, "amount_kopecks": total, "internal_cost": internal}

    def test_hash_is_stable_for_equivalent_json_and_sensitive_to_changes(self):
        original = self.snapshot()
        reordered = dict(reversed(list(original.items())))
        self.assertRegex(fingerprint(original), r"^[a-f0-9]{64}$")
        self.assertEqual(fingerprint(original), fingerprint(reordered))
        changed = copy.deepcopy(original)
        changed["items"][0]["quantity"] = "3.376"
        self.assertNotEqual(fingerprint(original), fingerprint(changed))

    def test_itemized_quote_matches_independent_server_calculation(self):
        s = self.snapshot()
        self.assertEqual(verify_totals(s, calculate), fingerprint(s))
        self.assertGreater(s["amount_kopecks"], 0)

    def test_tampered_amount_is_rejected(self):
        s = self.snapshot()
        s["amount_kopecks"] += 1
        with self.assertRaises(InvalidSnapshot):
            verify_totals(s, calculate)

    def test_tampered_line_tax_is_rejected_even_when_grand_total_matches(self):
        s = self.snapshot()
        s["items"][0]["tax_amount"] += 1
        with self.assertRaises(InvalidSnapshot):
            verify_totals(s, calculate)

    def test_optional_exclusion_and_non_itemized_legacy_quote(self):
        s = self.snapshot()
        self.assertFalse(s["items"][1]["included"])
        self.assertEqual(verify_totals(s, calculate), fingerprint(s))
        manual = {"title": "Ручной расчёт", "itemized": 0,
                  "items": [], "amount_kopecks": 10000, "internal_cost": 0}
        self.assertEqual(verify_totals(manual, calculate), fingerprint(manual))

    def test_money_matrix_matches_decimal_reference_with_optional_lines(self):
        from decimal import Decimal, ROUND_HALF_UP
        prices = (1, 100, 10001, 983040)
        quantities = ("0.0001", "0.5", "2.125", "99.9999")
        percentages = ("0", "5", "12.5", "20")
        # Deliberately exercise half-kopeck rounding and empty optional rows
        # without assuming a particular UI or Python float formatting.
        for index in range(128):
            quantity = quantities[index % len(quantities)]
            price = prices[(index // 4) % len(prices)]
            tax = percentages[(index // 16) % len(percentages)]
            discount = percentages[(index // 64) % len(percentages)]
            included = index % 7 != 0
            input_line = {
                "name": "Расчёт", "quantity": quantity,
                "unit_price": price, "tax": tax,
                "discount": discount, "optional": True,
                "included": included, "cost_price": min(price, 10000),
            }
            with self.subTest(index=index):
                rows, total, cost = calculate([
                    {"name": "Обязательная работа", "unit_price": 1000},
                    input_line,
                ])
                base = (
                    Decimal(quantity) * price *
                    (1 - Decimal(discount) / 100)
                ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                vat = (base * Decimal(tax) / 100).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
                reference = int(base + vat)
                self.assertEqual(rows[1]["subtotal"], reference)
                self.assertEqual(total, 1000 + (reference if included else 0))
                self.assertEqual(cost, rows[1]["internal_cost"] if included else 0)

    def test_invalid_inputs_fail_closed(self):
        for payload in (None, [], {"itemized": True, "amount_kopecks": 1, "items": []},
                        {"itemized": False, "amount_kopecks": True, "items": []}):
            with self.subTest(payload=payload), self.assertRaises(InvalidSnapshot):
                verify_totals(payload, calculate)


if __name__ == "__main__":
    unittest.main()
