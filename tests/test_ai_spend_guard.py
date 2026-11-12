"""Security regression for cross-route AI spend protection and log privacy."""

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend import ai, assistant, assistant_jobs
from backend.app import Handler
from backend.security_limits import AI_SPEND_PER_MINUTE, enforce_ai_spend


class AiCostBoundaryTests(unittest.TestCase):
    def test_shared_bucket_is_per_account_not_per_ip_or_route(self):
        handler = SimpleNamespace(throttle=Mock())
        account = SimpleNamespace(user={"id": "account-1"}, h=handler)
        enforce_ai_spend(account)
        handler.throttle.assert_called_once_with(
            "ai:spend:account-1", AI_SPEND_PER_MINUTE, 60
        )
        self.assertLessEqual(AI_SPEND_PER_MINUTE, 6)

    def test_every_cost_bearing_entrypoint_checks_shared_guard(self):
        self.assertIn("enforce_ai_spend(service)", inspect.getsource(assistant.route))
        self.assertIn("enforce_ai_spend(service)", inspect.getsource(ai._draft))
        self.assertIn("enforce_ai_spend(service)", inspect.getsource(assistant_jobs.route))
        route = inspect.getsource(assistant_jobs.route)
        self.assertLess(route.index("if existing:"), route.index("service.h.throttle('assistant:'"))
        self.assertLess(route.index("if count >= 2:"), route.index("enforce_ai_spend(service)"))
        self.assertLess(route.index("if count >= 50:"), route.index("enforce_ai_spend(service)"))
        self.assertLess(route.index("enforce_ai_spend(service)"), route.index("reservation = assistant.reserve_in_transaction"))

    def test_http_access_log_redacts_long_path_segments(self):
        request = Handler.__new__(Handler)
        request.path = "/api/public/files/secret_token_value_abcdefghijklmnopqrstuvwxyz"
        request.command = "GET"
        request.request_id = "test-id"
        with patch("builtins.print") as output:
            request.log_message('%s %s', "GET", "200")
        payload = json.loads(output.call_args.args[0])
        self.assertEqual(payload["path"], "/api/public/files/[redacted]")
        self.assertNotIn("secret_token_value", output.call_args.args[0])
