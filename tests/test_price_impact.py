"""Read-only supplier price impact calculations must not alter estimates."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend import business, product_sources
from backend.price_impact import calculate_price_impact

NOW = 1_800_000_000


def line(**updates):
    item = {
        "line_id": "line-1", "name": "Кабель", "quantity": "5", "unit": "м",
        "unit_price": 10000, "subtotal": 66000, "coefficient": "1",
        "markup": "10", "discount": "0", "tax": "20", "included": True,
    }
    item.update(updates)
    return item


def source(**updates):
    entry = {
        "id": "source-1", "quote_item_id": "line-1", "monitored": 1,
        "source_status": "active", "price_kopecks": 12000, "currency": "RUB",
        "unit": "м", "availability": "in_stock", "last_checked_at": NOW - 100,
        "url": "https://example.test/supplier",
    }
    entry.update(updates)
    return entry


def quote(**updates):
    item = {
        "id": "quote-1", "revision": 7, "currency": "RUB",
        "amount_kopecks": 120000, "items": [line()],
    }
    item.update(updates)
    return item


class PriceImpactTests(unittest.TestCase):
    def test_modifier_aware_exact_kopeck_arithmetic(self):
        actual = calculate_price_impact(quote(), [source()], NOW)
        self.assertEqual(actual["comparable_lines"], 1)
        self.assertEqual(actual["lines"][0]["quote_subtotal_kopecks"], 66000)
        self.assertEqual(actual["lines"][0]["indicative_subtotal_kopecks"], 79200)
        self.assertEqual(actual["comparable_delta_kopecks"], 13200)
        self.assertEqual(actual["indicative_total_kopecks"], 133200)
        self.assertEqual(actual["lines"][0]["delta_percent"], "20.00")
        self.assertFalse(actual["financial_price_changed"])
        self.assertTrue(actual["observation_only"])

    def test_price_declines_are_not_hidden(self):
        actual = calculate_price_impact(quote(), [source(price_kopecks=9000)], NOW)
        self.assertEqual(actual["comparable_delta_kopecks"], -6600)
        self.assertEqual(actual["lines"][0]["delta_percent"], "-10.00")

    def test_zero_original_price_not_divided_by_zero(self):
        original = quote(items=[line(unit_price=0, subtotal=0)])
        actual = calculate_price_impact(original, [source(price_kopecks=100)], NOW)
        self.assertEqual(actual["lines"][0]["delta_percent"], None)
        self.assertEqual(actual["lines"][0]["indicative_subtotal_kopecks"], 660)

    def test_skips_incompatible_or_stale_prices_without_changing_total(self):
        candidates = (
            (source(currency="USD"), "currency_mismatch"),
            (source(unit="шт."), "unit_mismatch"),
            (source(unit=""), "unit_mismatch"),
            (source(last_checked_at=NOW - 40 * 86400), "stale"),
            (source(last_checked_at=NOW + 10_000), "stale"),
            (source(price_kopecks=None), "invalid_price"),
            (source(availability="out_of_stock"), "out_of_stock"),
        )
        for supplier, status in candidates:
            with self.subTest(status=status):
                actual = calculate_price_impact(quote(), [supplier], NOW)
                self.assertEqual(actual["lines"][0]["status"], status)
                self.assertEqual(actual["comparable_lines"], 0)
                self.assertEqual(actual["comparable_delta_kopecks"], 0)
                self.assertEqual(actual["indicative_total_kopecks"], 120000)

    def test_exact_unit_aliases_allowed_without_conversion(self):
        sample = calculate_price_impact(
            quote(items=[line(unit="шт.")]), [source(unit="штук")], NOW
        )
        self.assertEqual(sample["comparable_lines"], 1)
        squared = calculate_price_impact(
            quote(items=[line(unit="м²")]), [source(unit="м2")], NOW
        )
        self.assertEqual(squared["comparable_lines"], 1)
        wrong_dimension = calculate_price_impact(
            quote(items=[line(unit="м²")]), [source(unit="м")], NOW
        )
        self.assertEqual(wrong_dimension["lines"][0]["status"], "unit_mismatch")

    def test_skips_excluded_lines(self):
        actual = calculate_price_impact(quote(items=[line(included=False)]), [source()], NOW)
        self.assertEqual(actual["lines"][0]["status"], "skipped")
        self.assertEqual(actual["comparable_lines"], 0)

    def test_multi_provider_is_ambiguous_not_average(self):
        actual = calculate_price_impact(quote(), [source(), source(id="source-2", price_kopecks=8000)], NOW)
        self.assertEqual(actual["lines"][0]["status"], "ambiguous")
        self.assertEqual(actual["comparable_lines"], 0)

    def test_does_not_mutate_quote_or_sources(self):
        q, links = quote(), [source()]
        before_q, before_links = copy.deepcopy(q), copy.deepcopy(links)
        calculate_price_impact(q, links, NOW)
        self.assertEqual(q, before_q)
        self.assertEqual(links, before_links)

    def test_only_matching_quote_lines_count(self):
        actual = calculate_price_impact(quote(), [source(quote_item_id="unrelated")], NOW)
        self.assertEqual(actual["linked_lines"], 0)
        self.assertEqual(actual["comparable_lines"], 0)



class PriceImpactRouteTests(unittest.TestCase):
    def test_quote_lookup_and_supplier_query_are_workspace_scoped(self):
        service = SimpleNamespace(
            wid="workspace-1", con=MagicMock(),
            get=MagicMock(return_value={"id": "quote-1"}),
            quote_view=MagicMock(return_value=quote()),
        )
        service.con.execute.return_value.fetchall.return_value = [source()]
        with patch.object(product_sources, "_premium_access", return_value={"plan": "pro_plus"}), \
                patch.object(product_sources, "_now", return_value=NOW):
            status, report = product_sources.route(
                service, "GET", ["price-impact"], {"quote_id": ["quote-1"]}, {}
            )
        self.assertEqual(status, 200)
        self.assertEqual(report["comparable_lines"], 1)
        service.get.assert_called_once_with("quotes", "quote-1")
        sql, params = service.con.execute.call_args.args
        self.assertIn("workspace_id=?", sql)
        self.assertIn("quote_id=?", sql)
        self.assertEqual(params, ("workspace-1", "quote-1"))

    def test_downgraded_plans_fail_before_quote_access(self):
        service = SimpleNamespace(wid="workspace-1", con=MagicMock(), get=MagicMock())
        with patch.object(product_sources, "_premium_access",
                          side_effect=business.DomainError(402, "Upgrade")):
            with self.assertRaises(business.DomainError) as error:
                product_sources.route(
                    service, "GET", ["price-impact"], {"quote_id": ["quote-1"]}, {}
                )
        self.assertEqual(error.exception.status, 402)
        service.get.assert_not_called()

    def test_foreign_quote_is_not_read(self):
        service = SimpleNamespace(
            wid="workspace-1", con=MagicMock(),
            get=MagicMock(side_effect=business.DomainError(404, "Not found")),
        )
        with patch.object(product_sources, "_premium_access", return_value={"plan": "team"}):
            with self.assertRaises(business.DomainError) as error:
                product_sources.route(
                    service, "GET", ["price-impact"], {"quote_id": ["quote-foreign"]}, {}
                )
        self.assertEqual(error.exception.status, 404)
        service.con.execute.assert_not_called()



if __name__ == "__main__":
    unittest.main()
