import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from backend import redis_infra
from backend import ai, assistant
from backend.app import ApiError, Handler
from backend.business import DomainError


class FakeClient:
    def __init__(self):
        self.values = {}

    def set(self, name, value, nx=False, ex=None):
        if nx and name in self.values:
            return False
        self.values[name] = (value, ex)
        return True

    def eval(self, script, keys, args):
        if "DEL" in script:
            name = keys[0]
            if name in self.values and self.values[name][0] == args[0]:
                del self.values[name]
                return 1
            return 0
        return [1, 0]


class RedisInfraTests(unittest.TestCase):
    def test_keys_are_environment_scoped_and_never_contain_pii(self):
        with patch.dict(os.environ, {"REDIS_ENV": "preview"}):
            preview = redis_infra.key("ratelimit", "person@example.test")
        with patch.dict(os.environ, {"REDIS_ENV": "production"}):
            production = redis_infra.key("ratelimit", "person@example.test")
        self.assertNotEqual(preview, production)
        self.assertNotIn("person@example.test", preview)
        self.assertTrue(preview.startswith("smetra:preview:ratelimit:"))

    def test_lock_conflict_wrong_owner_and_release(self):
        fake = redis_infra.RedisProvider(FakeClient())
        with patch("backend.redis_infra.provider", return_value=fake):
            identity = uuid.uuid4().hex
            first = redis_infra.acquire_lock("assistant", identity, ttl=30)
            self.assertIsNotNone(first)
            self.assertIsNone(redis_infra.acquire_lock("assistant", identity, ttl=30))
            redis_infra.Lease(fake, first.name, "wrong").release()
            self.assertIn(first.name, fake.client.values)
            first.release()
            self.assertNotIn(first.name, fake.client.values)

    def test_redis_rate_limit_decision_and_outage_policy(self):
        target = Handler.__new__(Handler)
        with patch("backend.redis_infra.rate_limit", return_value=redis_infra.LimitResult(False, 7)):
            with self.assertRaises(ApiError) as denied:
                target.throttle("login:test", 10, 60)
        self.assertEqual(denied.exception.status, 429)
        self.assertEqual(target.retry_after, 7)
        with patch("backend.redis_infra.rate_limit", side_effect=redis_infra.RedisUnavailable()):
            with self.assertRaises(ApiError) as blocked:
                target.throttle("assistant:test", 10, 60)
        self.assertEqual(blocked.exception.status, 503)
        with patch("backend.redis_infra.rate_limit", side_effect=redis_infra.RedisUnavailable()), patch.dict(os.environ, {"DATABASE_URL": ""}):
            target.throttle("ordinary:" + uuid.uuid4().hex, 10, 60)

    def test_provider_requires_ttl_for_ephemeral_writes(self):
        fake = redis_infra.RedisProvider(FakeClient())
        with self.assertRaises(ValueError):
            fake.set("temporary", "value", 0)
        with self.assertRaises(ValueError):
            fake.set_nx("lock", "owner", 0)
        self.assertTrue(fake.set_nx("lock", "owner", 10))
        self.assertEqual(fake.client.values["lock"], ("owner", 10))

    def test_concurrent_ai_request_does_not_consume_monthly_quota(self):
        handler = SimpleNamespace(throttle=lambda *args: None)
        service = SimpleNamespace(user={"id": "user-1"}, wid="workspace-1", h=handler)
        with patch("backend.assistant.available", return_value=True), patch(
            "backend.redis_infra.acquire_lock", return_value=None
        ), patch("backend.assistant.reserve") as reserve:
            with self.assertRaises(DomainError) as denied:
                assistant.route(service, "POST", ["chat"], {"text": "Помоги со сметой"})
        self.assertEqual(denied.exception.status, 429)
        self.assertEqual(handler.retry_after, 5)
        reserve.assert_not_called()

    def test_concurrent_ai_draft_is_rejected_before_provider_call(self):
        handler = SimpleNamespace()
        service = SimpleNamespace(user={"id": "user-1"}, h=handler)
        with patch("backend.redis_infra.acquire_lock", return_value=None):
            with self.assertRaises(DomainError) as denied:
                ai.draft(service, {"text": "Составь смету"})
        self.assertEqual(denied.exception.status, 429)
        self.assertEqual(handler.retry_after, 5)


if __name__ == "__main__":
    unittest.main()
