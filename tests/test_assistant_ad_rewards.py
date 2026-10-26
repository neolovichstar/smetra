import os
import time
import unittest
from unittest.mock import patch

from backend import ai_tokens
from tests.test_business import BusinessFlows


class AssistantAdRewardTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp
    call = BusinessFlows.call
    account = BusinessFlows.account

    def exhaust_free_quota(self, user_id):
        """The monthly token allowance is spent; only the wallet can help now."""
        with self.mod.db() as con:
            con.execute(
                "INSERT INTO rate_limits(key,count,started) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET count=excluded.count",
                (ai_tokens.month_key(user_id), 10**9, int(time.time())),
            )

    def test_reward_claim_is_atomic_daily_and_adds_wallet_tokens(self):
        token, user_id = self.account("rewarded-ad-owner")
        self.exhaust_free_quota(user_id)
        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            status, offer = self.call("/assistant/ad-reward", token=token)
            self.assertEqual(status, 200, offer)
            self.assertTrue(offer["available"])
            self.assertEqual((offer["amount"], offer["unit"]), (ai_tokens.AD_REWARD_TOKENS, "tokens"))
            self.assertEqual(offer["ad_unit_id"], "test-reward-placement")

            status, attempt = self.call("/assistant/ad-reward", "POST", {"operation": "start"}, token)
            self.assertEqual(status, 200, attempt)
            status, claimed = self.call("/assistant/ad-reward", "POST", attempt, token)
            self.assertEqual(status, 200, claimed)
            self.assertEqual(claimed["granted"], ai_tokens.AD_REWARD_TOKENS)
            self.assertEqual(claimed["quota"]["remaining"], ai_tokens.AD_REWARD_TOKENS)
            self.assertEqual(claimed["quota"]["wallet"], ai_tokens.AD_REWARD_TOKENS)

            status, repeated = self.call("/assistant/ad-reward", "POST", attempt, token)
            self.assertEqual(status, 200, repeated)
            self.assertTrue(repeated["replayed"])
            self.assertEqual(self.call("/assistant/ad-reward", token=token)[1]["available"], False)
            self.assertEqual(self.call("/assistant", token=token)[1]["quota"]["remaining"], ai_tokens.AD_REWARD_TOKENS)

            usage = {"prompt_tokens": 8000, "completion_tokens": 2000, "total_tokens": 10000}
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}), patch(
                "backend.assistant.query_model", return_value={"content": "Ещё один ответ", "_usage": usage}
            ):
                status, result = self.call("/assistant/chat", "POST", {"text": "Первый бонусный запрос"}, token)
            self.assertEqual(status, 200, result)
            self.assertEqual(result["quota"]["wallet"], ai_tokens.AD_REWARD_TOKENS - 10000)

    def test_rewarding_requires_real_config_and_quota_exhaustion(self):
        token, user_id = self.account("rewarded-ad-config")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("YANDEX_REWARDED_AD_UNIT_ID", None)
            status, offer = self.call("/assistant/ad-reward", token=token)
            self.assertEqual(status, 200, offer)
            self.assertFalse(offer["enabled"])
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {}, token)[0], 503)

        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            # With monthly tokens remaining the offer stays hidden.
            self.assertFalse(self.call("/assistant/ad-reward", token=token)[1]["available"])

        self.exhaust_free_quota(user_id)
        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            self.assertTrue(self.call("/assistant/ad-reward", token=token)[1]["available"])

    def test_claim_rejects_forgery_expiry_and_other_account(self):
        token, user_id = self.account("ad-attempt-owner")
        other, _ = self.account("ad-attempt-other")
        self.exhaust_free_quota(user_id)
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

    def test_legacy_request_credits_become_wallet_tokens_once(self):
        token, user_id = self.account("ad-credit-ledger")
        self.exhaust_free_quota(user_id)
        now = int(time.time())
        with self.mod.db() as con:
            con.execute(
                "INSERT INTO assistant_ad_attempts(id,user_id,nonce_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?)",
                ("legacy-attempt", user_id, "x", "completed", now, now + 600),
            )
            con.execute(
                "INSERT INTO assistant_ad_reward_credits(id,user_id,attempt_id,reward_date,amount,remaining,created_at,expires_at) "
                "VALUES(?,?,?,?,3,2,?,?)",
                ("legacy-credit", user_id, "legacy-attempt", "2000-01-01", now, now + 86400),
            )
        first = self.call("/assistant", token=token)[1]["quota"]
        second = self.call("/assistant", token=token)[1]["quota"]
        self.assertEqual(first["wallet"], 2 * ai_tokens.REQUEST_TOKENS)
        self.assertEqual(second["wallet"], 2 * ai_tokens.REQUEST_TOKENS)

    def test_paid_plan_cannot_claim_rewarded_ads(self):
        token, user_id = self.account("rewarded-ad-pro")
        with self.mod.db() as con:
            con.execute(
                "UPDATE users SET plan='pro',entitlement_until=? WHERE id=?",
                (int(time.time()) + 86400, user_id),
            )
        self.exhaust_free_quota(user_id)
        with patch.dict(os.environ, {"YANDEX_REWARDED_AD_UNIT_ID": "test-reward-placement"}):
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {}, token)[0], 403)


if __name__ == "__main__":
    unittest.main()
