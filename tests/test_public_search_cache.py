"""Regression checks for cost-aware, isolated public web search caching."""
import json
import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from backend import internet_search, redis_infra
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


if __name__ == "__main__":
    import unittest
    unittest.main()
