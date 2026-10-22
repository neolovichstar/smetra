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

            status, claimed = self.call("/assistant/ad-reward", "POST", {}, token)
            self.assertEqual(status, 200, claimed)
            self.assertEqual(claimed["granted"], 3)
            self.assertEqual(claimed["quota"]["remaining"], 3)
            self.assertEqual(claimed["quota"]["ad_reward_remaining"], 3)

            status, repeated = self.call("/assistant/ad-reward", "POST", {}, token)
            self.assertEqual(status, 409, repeated)
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

        self.exhaust_free_quota(token)
        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            self.assertFalse(self.call("/assistant/ad-reward", token=token)[1]["available"])

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
