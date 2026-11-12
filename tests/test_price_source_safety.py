"""Financial and privacy regressions for price sourcing and AI search."""
import inspect
import os
import unittest
from unittest.mock import Mock, patch

from backend import assistant, internet_search, product_sources
from backend.business import DomainError


class ProductPriceFormatTests(unittest.TestCase):
    def test_currency_format_and_decimal_cents(self):
        valid = {
            "1200": 120000,
            "1 200": 120000,
            "1\u00a0200,50 ₽": 120050,
            "1\u202f200,50": 120050,
            "1.200,50": 120050,
            "1,200.50": 120050,
            "1.234.567": 123456700,
            "1,234,567": 123456700,
            "12 345 678,90 руб.": 1234567890,
            "1299.99": 129999,
            "1299,99": 129999,
            "1200 RUB": 120000,
            1200: 120000,
            12.5: 1250,
        }
        for value, expected in valid.items():
            with self.subTest(value=value):
                self.assertEqual(product_sources._price_to_kopecks(value), expected)

    def test_dangerous_or_ambiguous_price_is_unknown(self):
        invalid = (
            "1.200", "1,200", "2.500", "123 45", "300-500",
            "от 900 руб.", "900 ₽ за 30 кг", "900 ₽ и 1000 ₽",
            "руб 800", "-100", "12,123", True, None, float("nan"),
            "1e9", "1.200,000", "12 34 567", "1 000 00",
        )
        for value in invalid:
            with self.subTest(value=value):
                self.assertIsNone(product_sources._price_to_kopecks(value))


class PublicSearchGuardTests(unittest.TestCase):
    def test_private_phone_and_signed_link_never_reach_provider(self):
        service = type("Service", (), {
            "user": {"id": "user"}, "h": type("Handler", (), {"throttle": Mock()})(),
        })()
        with patch.dict(os.environ, {
            "OPENROUTER_API_KEY": "fixture-only-not-real-0123456789",
            "SMETRA_SEARCH_BACKEND": "openrouter",
        }), patch("backend.internet_search._openrouter_search") as external:
            for query in (
                "штукатурка +7 (999) 123-45-67",
                "цена ремонта 89991234567",
                "https://example.org/file?signature=verysecret цена",
                "https://example.org/file?access_token=abc цена",
            ):
                with self.subTest(query=query), self.assertRaises(DomainError):
                    internet_search.public_search(service, query)
            external.assert_not_called()

    def test_paid_assistant_does_not_bypass_guarded_web_search(self):
        available = {tool["function"]["name"] for tool in assistant.tools()}
        self.assertIn("search_internet", available)
        self.assertIn("search_market_prices", available)
        stream = assistant._stream_payload(
            "anthropic/claude-haiku-5.5",
            [{"role": "user", "content": "Найди цену на бетон"}],
            paid_model=True,
        )
        self.assertTrue(any(tool["function"]["name"] == "search_internet"
                            for tool in stream["tools"]))
        self.assertFalse(any(tool.get("type") == "openrouter:web_search"
                             for tool in stream["tools"]))
        self.assertNotIn('"type": "openrouter:web_search"',
                         inspect.getsource(assistant.query_model))

    def test_gateway_sources_are_emitted_only_for_safe_links(self):
        listener = Mock()
        assistant._emit_public_sources(listener, {"results": [
            {"url": "https://supplier.example.org/price", "title": "Прайс"},
            {"url": "https://supplier.example.org/price"},
            {"url": "http://127.0.0.1/private"},
            {"url": "file:///etc/passwd"},
            {"url": "https://second.example.org/price"},
        ]})
        self.assertEqual(listener.call_count, 2)
        self.assertEqual(listener.call_args_list[0].args[0],
                         {"url": "https://supplier.example.org/price",
                          "domain": "supplier.example.org"})
        self.assertEqual(listener.call_args_list[1].args[0]["domain"],
                         "second.example.org")


if __name__ == "__main__":
    unittest.main()
