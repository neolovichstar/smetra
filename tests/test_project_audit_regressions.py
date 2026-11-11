"""Regress failures found during the cross-project stability audit."""
import os
import time
import uuid
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.business import DomainError
from backend import assistant_files
from tests import test_business


class AuditValidationTests(unittest.TestCase):
    def test_bad_ai_file_queries_are_clean_client_errors(self):
        # Invalid model arguments must not terminate a whole chat with a 500.
        for raw in (None, 3, ["file"], {"query": "secret"}):
            with self.subTest(raw=raw):
                for func in (assistant_files.list_files, assistant_files.search_content):
                    with self.assertRaises(DomainError) as error:
                        func(None, raw)
                    self.assertEqual(error.exception.status, 400)


class FailedDraftLimitTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_older_failed_drafts_do_not_exhaust_20_successful_requests(self):
        token, user_id = self.account("failed-ai-draft-quota")
        workspace = self.call("/workspace", token=token)[1]["workspace"]["id"]
        with self.mod.db() as con:
            for index in range(21):
                con.execute(
                    "INSERT INTO ai_usage(id,workspace_id,user_id,action,model,status,created_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), workspace, user_id, "estimate_draft",
                     "test-model", "failed", int(time.time())),
                )
        # One provider failure must reach the provider path (502), instead
        # of rejecting the user for a quota exhausted by previous failures.
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-provider-only"}), patch(
            "backend.redis_infra.acquire_lock",
            return_value=SimpleNamespace(release=lambda: None),
        ), patch("backend.ai.open_completion", side_effect=TimeoutError):
            code, result = self.call("/ai/draft", "POST", {"text": "Рассчитай отделку кухни"}, token)
        self.assertEqual(code, 502, result)
        self.assertNotIn("20 запросов", str(result))


if __name__ == "__main__":
    unittest.main()
