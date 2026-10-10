import copy
import unittest

from backend.business import DomainError, calculate
from backend.quote_versions import carry_identities, compare


def quote(items, **values):
    rows, total, cost = calculate(items)
    return {"items": rows, "amount_kopecks": total, "internal_cost": cost, "currency": "RUB", **values}


class QuoteComparisonTests(unittest.TestCase):
    def test_older_clients_keep_matching_ids_without_guessing_renames(self):
        before = quote([{"name": "A", "unit_price": 100}, {"name": "B", "unit_price": 200}])
        supplied = [{"name": "A", "unit_price": 150}, {"name": "B", "unit_price": 200}]
        after = quote(supplied)
        after["items"] = carry_identities(before["items"], after["items"], supplied)
        result = compare(before, after)
        self.assertEqual(result["summary"]["changed"], 1)
        self.assertEqual(result["summary"]["unchanged"], 1)
        self.assertEqual(result["summary"]["added"], 0)
        renamed = [{"name": "Unknown replacement", "unit_price": 100}]
        after = quote(renamed)
        after["items"] = carry_identities(before["items"], after["items"], renamed)
        self.assertNotEqual(after["items"][0]["line_id"], before["items"][0]["line_id"])

    def test_stable_identity_tracks_rename_price_and_private_cost(self):
        before = quote([{"name": "Work", "unit_price": 1000, "cost_price": 300}])
        after = quote([{**before["items"][0], "name": "Renamed", "unit_price": 2000, "cost_price": 500}])
        untouched = copy.deepcopy(before)
        result = compare(before, after)
        self.assertEqual(result["summary"]["changed"], 1)
        self.assertEqual(result["items"][0]["fields"], ["name", "unit_price", "cost_price"])
        self.assertEqual(result["totals"]["delta_kopecks"], 1000)
        self.assertEqual(before, untouched)

    def test_new_ids_preserved_and_invalid_duplicate_ids_rejected(self):
        rows, _, _ = calculate([{"name": "A", "unit_price": 100}])
        self.assertEqual(calculate(rows)[0][0]["line_id"], rows[0]["line_id"])
        for value in (True, 1, None, "", "<script>", "x" * 65):
            with self.assertRaises(DomainError):
                calculate([{"name": "A", "unit_price": 100, "line_id": value}])
        with self.assertRaises(DomainError):
            calculate(rows * 2)

    def test_reordering_is_distinct_from_added_rows_shifting_positions(self):
        before = quote([{"name": "A", "unit_price": 100}, {"name": "B", "unit_price": 200}])
        after = quote(list(reversed(before["items"])))
        self.assertEqual(compare(before, after)["summary"]["moved"], 2)
        after = quote([{"name": "C", "unit_price": 400}, *before["items"]])
        result = compare(before, after)
        self.assertEqual(result["summary"]["added"], 1)
        self.assertEqual(result["summary"]["moved"], 0)
        self.assertEqual(result["summary"]["unchanged"], 2)

    def test_legacy_duplicate_names_match_identical_occurrences_first(self):
        before = quote([{"name": "A", "unit_price": 100}, {"name": "A", "unit_price": 200}])
        after = quote([{"name": "A", "unit_price": 200}, {"name": "A", "unit_price": 150}])
        for snapshot in (before, after):
            for row in snapshot["items"]:
                del row["line_id"]
        result = compare(before, after)
        self.assertEqual(result["summary"]["added"], 0)
        self.assertEqual(result["summary"]["removed"], 0)
        self.assertEqual(result["summary"]["changed"], 1)

    def test_currency_change_never_subtracts_unrelated_minor_units(self):
        before = quote([{"name": "A", "unit_price": 100}])
        after = quote([{**before["items"][0], "unit_price": 200}], currency="USD")
        result = compare(before, after)
        self.assertIsNone(result["totals"]["delta_kopecks"])
        self.assertIsNone(result["items"][0]["delta_kopecks"])
        self.assertIn("currency", [row["field"] for row in result["fields"]])

    def test_optional_excluded_price_does_not_change_total(self):
        before = quote([{"name": "A", "unit_price": 100}, {"name": "Option", "unit_price": 500, "optional": True, "included": False}])
        after = quote([{**row, "unit_price": 900} if row["optional"] else row for row in before["items"]])
        result = compare(before, after)
        self.assertEqual(result["totals"]["delta_kopecks"], 0)
        self.assertEqual(result["items"][0]["delta_kopecks"], 0)

    def test_decimal_formatting_and_unchanged_legacy_rows_are_not_changes(self):
        before = quote([{"name": "A", "unit_price": 100}])
        after = quote([{**before["items"][0], "quantity": "1.0000"}])
        self.assertFalse(compare(before, after)["has_changes"])
        del before["items"][0]["line_id"]
        self.assertFalse(compare(before, after)["has_changes"])

    def test_added_removed_and_metadata_changes_are_reported(self):
        before = quote([{"name": "A", "unit_price": 100}], terms="Before", due_date="2026-10-10")
        after = quote([{"name": "B", "unit_price": 300}], terms="After", due_date="2026-10-20")
        result = compare(before, after)
        self.assertEqual((result["summary"]["added"], result["summary"]["removed"]), (1, 1))
        self.assertEqual([row["field"] for row in result["fields"]], ["terms", "due_date"])
        self.assertEqual(sum(row["delta_kopecks"] for row in result["items"]), result["totals"]["delta_kopecks"])
