"""Regression checks for cost-aware, isolated public web search caching."""
import json
import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from backend import internet_search
from backend.business import DomainError


class _Cache:
    def __init__(self):
        self.items = {}
        self.ttls = []

    def get(self, key):
        return self.items.get(key)

    def set(self, key, value, ttl):
        self.items[key] = value
        self.ttls.append(ttl)


class PublicSearchCacheTests(TestCase):
    def test_reuses_public_results_without_recharging_provider_limit(self):
        cache, throttle = _Cache(), Mock()
        user = SimpleNamespace(user={"id": "team-a"}, h=SimpleNamespace(throttle=throttle))
        other = SimpleNamespace(user={"id": "team-b"}, h=SimpleNamespace(throttle=throttle))
        payload = {"results": [{"title": "Цена штукатурки", "url": "https://example.org/cost", "content": "Публичный прайс-лист"}]}
        env = {"TAVILY_API_KEY": "fixture-not-real-provider-key", "SMETRA_SEARCH_BACKEND": "tavily", "REDIS_ENV": "preview"}
        with patch.dict(os.environ, env), patch("backend.redis_infra.provider", return_value=cache), patch(
            "backend.internet_search._tavily_search", return_value=(payload, "Tavily")
        ) as search:
            first = internet_search.public_search(user, "цена штукатурки")
            second = internet_search.public_search(user, "ЦЕНА ШТУКАТУРКИ")
            third = internet_search.public_search(other, "цена штукатурки")

        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(len(cache.items), 1)
        self.assertEqual(cache.ttls, [180])
        self.assertTrue(all(key.startswith("smetra:preview:publicsearch:") for key in cache.items))
        self.assertEqual(json.loads(next(iter(cache.items.values())))["source"], "Tavily")
        self.assertEqual(
            [c.args[0] for c in throttle.call_args_list],
            ["smetra-search:user:team-a", "smetra-search:global",
             "smetra-search:cached:team-a", "smetra-search:cached:team-b"],
        )
        self.assertEqual([c.args[1:] for c in throttle.call_args_list], [(6, 60), (200, 3600), (30, 60), (30, 60)])

    def test_cache_isolation_and_no_personal_queries_or_plaintext_keys(self):
        env = {"TAVILY_API_KEY": "fixture-not-real-provider-key", "SMETRA_SEARCH_BACKEND": "tavily"}
        cache = _Cache()
        account = SimpleNamespace(user={"id": "user"}, h=SimpleNamespace(throttle=Mock()))
        payload = {"results": [{"title": "Метраж", "url": "https://example.org/public", "content": "Данные"}]}
        with patch.dict(os.environ, env), patch("backend.redis_infra.provider", return_value=cache), patch(
            "backend.internet_search._tavily_search", return_value=(payload, "Tavily")
        ) as search:
            with patch.dict(os.environ, {"REDIS_ENV": "preview"}):
                internet_search.public_search(account, "цена бетона")
                key_preview = next(iter(cache.items))
            with patch.dict(os.environ, {"REDIS_ENV": "production"}):
                internet_search.public_search(account, "цена бетона")
                self.assertEqual(len(cache.items), 2)
                key_production = next(key for key in cache.items if key != key_preview)
                with self.assertRaises(DomainError):
                    internet_search.public_search(account, "почта client@example.org")
        self.assertEqual(search.call_count, 2)
        self.assertNotEqual(key_preview, key_production)
        self.assertTrue(key_production.startswith("smetra:production:publicsearch:"))
        self.assertNotIn("цена бетона", key_production)

    def test_distinct_product_skus_survive_deduplication_and_private_links_do_not(self):
        payload = {"results": [
            {"url": "https://supplier.example.org/product?id=101", "title": "Кирпич 101"},
            {"url": "https://supplier.example.org/product?id=202", "title": "Кирпич 202"},
            {"url": "https://supplier.example.org/product?id=101#details", "title": "Дубликат"},
            {"url": "https://supplier.example.org/product?token=secret", "title": "Частная ссылка"},
            {"url": "https://supplier.example.org/product#access_token=secret", "title": "Токен в fragment"},
            {"url": "https://supplier.example.org/product?id=303\\nother", "title": "Управляющий символ"},
        ]}
        result = internet_search._normalize(payload, "OpenRouter", "цена кирпича")
        self.assertEqual([row["url"] for row in result["results"]], [
            "https://supplier.example.org/product?id=101",
            "https://supplier.example.org/product?id=202",
        ])
        self.assertIsNone(internet_search._safe_link("https://supplier.example.org/file?X-Amz-Signature=abc"))
        self.assertIsNone(internet_search._safe_link("https://supplier.example.org/file#token=abc"))

    def test_openrouter_annotations_are_used_instead_of_model_hallucinated_urls(self):
        service = SimpleNamespace(
            user={"id": "acc"}, h=SimpleNamespace(throttle=Mock())
        )
        responses = {
            "choices": [{
                "message": {
                    "content": "Самая дешёвая цена https://not-a-source.invalid",
                    "annotations": [
                        {"type": "url_citation", "url_citation": {
                            "url": "https://supplier.example.org/plaster",
                            "title": "Прайс производителя",
                            "content": "Штукатурка, цена в рублях за мешок",
                        }},
                        {"type": "url_citation", "url_citation": {
                            "url": "http://127.0.0.1/private",
                            "title": "Недопустимый URL",
                        }},
                    ],
                },
            }],
        }
        with patch.dict(os.environ, {
            "SMETRA_SEARCH_BACKEND": "openrouter",
            "OPENROUTER_API_KEY": "fixture-not-a-real-api-key",
            "REDIS_ENV": "test",
        }), patch("backend.redis_infra.provider", return_value=None), patch(
            "backend.internet_search._fetch_json", return_value=responses
        ) as fetcher:
            result = internet_search.public_search(service, "цена штукатурки")

        self.assertEqual(result["source"], "OpenRouter")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["url"], "https://supplier.example.org/plaster")
        self.assertNotIn("not-a-source", repr(result))
        self.assertIn("searched_at", result)
        request = fetcher.call_args.args[0]
        submitted = json.loads(request.data)
        self.assertEqual(submitted["tools"][0]["type"], "openrouter:web_search")
        self.assertEqual(submitted["tools"][0]["parameters"]["max_uses"], 1)
        self.assertEqual(submitted["tools"][0]["parameters"]["engine"], "parallel")
        self.assertEqual(submitted["max_tool_calls"], 1)
        self.assertIn("smetra-search:openrouter:global", [
            c.args[0] for c in service.h.throttle.call_args_list
        ])

    def test_search_requires_real_citations_and_never_caches_hallucinations(self):
        cache = _Cache()
        account = SimpleNamespace(user={"id": "acc"}, h=SimpleNamespace(throttle=Mock()))
        with patch.dict(os.environ, {
            "SMETRA_SEARCH_BACKEND": "openrouter",
            "OPENROUTER_API_KEY": "fixture-not-a-real-api-key",
            "REDIS_ENV": "test",
        }), patch("backend.redis_infra.provider", return_value=cache), patch(
            "backend.internet_search._fetch_json",
            return_value={"choices": [{"message": {"content": "https://fake.example"}}]},
        ):
            with self.assertRaises(DomainError) as error:
                internet_search.public_search(account, "цена кирпича")
        self.assertEqual(error.exception.status, 502)
        self.assertEqual(cache.items, {})

    def test_auto_uses_connected_openrouter_with_no_optional_search_keys(self):
        account = SimpleNamespace(user={"id": "acc"}, h=SimpleNamespace(throttle=Mock()))
        result = {"results": [{"title": "Прайс", "url": "https://example.org/price", "content": "Открытые цены"}]}
        with patch.dict(os.environ, {
            "SMETRA_SEARCH_BACKEND": "auto",
            "SMETRA_SEARXNG_URL": "",
            "TAVILY_API_KEY": "",
            "OPENROUTER_API_KEY": "fixture-not-a-real-api-key",
            "REDIS_ENV": "test",
        }), patch("backend.redis_infra.provider", return_value=None), patch(
            "backend.internet_search._openrouter_search",
            return_value=(result, "OpenRouter")
        ) as openrouter:
            out = internet_search.public_search(account, "цена утеплителя")
        openrouter.assert_called_once_with(account, "цена утеплителя")
        self.assertEqual(out["source"], "OpenRouter")

    def test_price_tool_keeps_search_evidence_unconfirmed(self):
        account = SimpleNamespace(user={"id": "acc"}, h=SimpleNamespace(throttle=Mock()))
        fake = {"query": "q", "source": "OpenRouter",
                "results": [{"title": "Прайс", "url": "https://example.org/price", "excerpt": "От 500 руб"}]}
        with patch("backend.internet_search.public_search", return_value=fake) as search:
            outcome = internet_search.market_price_sources(
                account, "Штукатурка", "мешок", "Москва", "material"
            )
        self.assertEqual(outcome["price_status"], "needs_review")
        self.assertEqual(outcome["currency"], "RUB")
        self.assertIn("Москва", search.call_args.args[1])
        with self.assertRaises(DomainError):
            internet_search.market_price_sources(account, "Кирпич", kind="invalid")

    def test_openrouter_http_402_reports_unavailable_without_leaking_credentials(self):
        from urllib.error import HTTPError
        from io import BytesIO

        account = SimpleNamespace(user={"id": "acc"}, h=SimpleNamespace(throttle=Mock()))
        with patch.dict(os.environ, {
            "SMETRA_SEARCH_BACKEND": "openrouter",
            "OPENROUTER_API_KEY": "fixture-not-a-real-api-key",
            "REDIS_ENV": "test",
        }), patch("backend.redis_infra.provider", return_value=None), patch(
            "backend.internet_search._fetch_json",
            side_effect=HTTPError("https://openrouter.ai/api/v1/chat/completions", 402, "no credit", {}, BytesIO()),
        ):
            with self.assertRaises(DomainError) as error:
                internet_search.public_search(account, "цена краски")
        self.assertEqual(error.exception.status, 503)
        self.assertNotIn("fixture-not-a-real-api-key", str(error.exception))


if __name__ == "__main__":
    import unittest
    unittest.main()
