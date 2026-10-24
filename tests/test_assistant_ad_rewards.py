import os
import unittest
from unittest.mock import patch

from tests.test_business import BusinessFlows


class AssistantAdRewardTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp
    call = BusinessFlows.call
    account = BusinessFlows.account

    def exhaust_free_quota(self, token):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}), patch(
            "backend.assistant.query_model", return_value={"content": "Проверенный ответ"}
        ):
            for index in range(3):
                code, result = self.call(
                    "/assistant/chat", "POST", {"text": "Проверка лимита " + str(index)}, token
                )
                self.assertEqual(code, 200, result)

    def test_reward_claim_is_atomic_daily_and_adds_three_usable_requests(self):
        token, _ = self.account("rewarded-ad-owner")
        self.exhaust_free_quota(token)
        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            status, offer = self.call("/assistant/ad-reward", token=token)
            self.assertEqual(status, 200, offer)
            self.assertTrue(offer["available"])
            self.assertEqual(offer["amount"], 3)
            self.assertEqual(offer["ad_unit_id"], "test-reward-placement")

            status, attempt = self.call("/assistant/ad-reward", "POST", {"operation": "start"}, token)
            self.assertEqual(status, 200, attempt)
            status, claimed = self.call("/assistant/ad-reward", "POST", attempt, token)
            self.assertEqual(status, 200, claimed)
            self.assertEqual(claimed["granted"], 3)
            self.assertEqual(claimed["quota"]["remaining"], 3)
            self.assertEqual(claimed["quota"]["ad_reward_remaining"], 3)

            status, repeated = self.call("/assistant/ad-reward", "POST", attempt, token)
            self.assertEqual(status, 200, repeated)
            self.assertTrue(repeated["replayed"])
            self.assertEqual(self.call("/assistant/ad-reward", token=token)[1]["available"], False)
            self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["remaining"], 3)

            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}), patch(
                "backend.assistant.query_model", return_value={"content": "Ещё один ответ"}
            ):
                status, result = self.call("/assistant/chat", "POST", {"text": "Первый бонусный запрос"}, token)
            self.assertEqual(status, 200, result)
            self.assertEqual(result["quota"]["remaining"], 2)
            self.assertEqual(result["quota"]["ad_reward_remaining"], 2)

    def test_rewarding_requires_real_config_and_quota_exhaustion(self):
        token, _ = self.account("rewarded-ad-config")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("YANDEX_REWARDED_AD_UNIT_ID", None)
            status, offer = self.call("/assistant/ad-reward", token=token)
            self.assertEqual(status, 200, offer)
            self.assertFalse(offer["enabled"])
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {}, token)[0], 503)

        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            # With free quota remaining the offer must stay hidden.
            self.assertFalse(self.call("/assistant/ad-reward", token=token)[1]["available"])

        self.exhaust_free_quota(token)
        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            # Only after the three free monthly requests are exhausted does the offer appear.
            self.assertTrue(self.call("/assistant/ad-reward", token=token)[1]["available"])

    def test_claim_rejects_forgery_expiry_and_other_account(self):
        token, uid = self.account("ad-attempt-owner")
        other, _ = self.account("ad-attempt-other")
        self.exhaust_free_quota(token)
        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {}, token)[0], 400)
            status, attempt = self.call("/assistant/ad-reward", "POST", {"operation": "start"}, token)
            self.assertEqual(status, 200, attempt)
            self.assertEqual(self.call("/assistant/ad-reward", "POST", attempt, other)[0], 400)
            wrong = dict(attempt, nonce="forged")
            self.assertEqual(self.call("/assistant/ad-reward", "POST", wrong, token)[0], 400)
            with self.mod.db() as con:
                con.execute("UPDATE assistant_ad_attempts SET expires_at=0 WHERE id=?", (attempt["attempt_id"],))
            self.assertEqual(self.call("/assistant/ad-reward", "POST", attempt, token)[0], 410)

    def test_expired_credit_does_not_erase_new_credit_and_job_cancel_refunds_once(self):
        from backend import assistant
        from backend.business import Service
        from types import SimpleNamespace
        token, uid = self.account("ad-credit-ledger")
        self.exhaust_free_quota(token)
        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            attempt = self.call("/assistant/ad-reward", "POST", {"operation": "start"}, token)[1]
            self.assertEqual(self.call("/assistant/ad-reward", "POST", attempt, token)[0], 200)
        with self.mod.db() as con:
            user = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            service = Service(SimpleNamespace(), con, self.base)
            service.user = user
            service.wid = con.execute("SELECT id FROM workspaces WHERE owner_id=?", (uid,)).fetchone()["id"]
            reserved = assistant.reserve(service)
            self.assertEqual(assistant.quota(service)["remaining"], 2)
            con.execute("UPDATE assistant_ad_reward_credits SET expires_at=0 WHERE user_id=?", (uid,))
            self.assertEqual(assistant.quota(service)["remaining"], 0)
            # A second valid day grant is not penalized by yesterday's spent credit.
            con.execute("UPDATE assistant_ad_reward_credits SET expires_at=?,remaining=3 WHERE user_id=?", (assistant.stamp()+86400, uid))
            self.assertEqual(assistant.quota(service)["remaining"], 3)
            assistant.release(service, reserved)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only", "ASSISTANT_WORKER_SECRET": "x"*40}):
            status, job = self.call("/assistant/jobs", "POST",
                                   {"text": "Проверка возврата"}, token, key="ad-job-cancel-0001")
            self.assertEqual(status, 202, job)
            self.assertEqual(self.call("/assistant/jobs/" + job["job"]["id"], "DELETE", token=token)[0], 200)
            self.assertEqual(self.call("/assistant/jobs/" + job["job"]["id"], "DELETE", token=token)[0], 200)
            self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["ad_reward_remaining"], 3)

    def test_paid_plan_cannot_claim_rewarded_ads(self):
        token, user_id = self.account("rewarded-ad-pro")
        with self.mod.db() as con:
            con.execute(
                "UPDATE users SET plan='pro',entitlement_until=? WHERE id=?",
                (int(__import__("time").time()) + 86400, user_id),
            )
        self.exhaust_free_quota(token)
        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {}, token)[0], 403)


if __name__ == "__main__":
    unittest.main()
