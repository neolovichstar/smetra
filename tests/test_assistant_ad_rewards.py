import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
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
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "123456789"}):
            status, offer = self.call("/assistant/ad-reward", token=token)
            self.assertEqual(status, 200, offer)
            self.assertTrue(offer["available"])
            self.assertEqual((offer["amount"], offer["unit"]), (ai_tokens.AD_REWARD_TOKENS, "tokens"))
            self.assertEqual(offer["ad_unit_id"], "123456789")

            status, attempt = self.call("/assistant/ad-reward", "POST", {"operation": "start", "provider": "vk"}, token)
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
            os.environ.pop("VK_REWARDED_SLOT_ID", None)
            status, offer = self.call("/assistant/ad-reward", token=token)
            self.assertEqual(status, 200, offer)
            self.assertFalse(offer["enabled"])
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {}, token)[0], 503)

        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "123456789"}):
            # With monthly tokens remaining the offer stays hidden.
            self.assertFalse(self.call("/assistant/ad-reward", token=token)[1]["available"])

        self.exhaust_free_quota(user_id)
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "123456789"}):
            self.assertTrue(self.call("/assistant/ad-reward", token=token)[1]["available"])

    def test_claim_rejects_forgery_expiry_and_other_account(self):
        token, user_id = self.account("ad-attempt-owner")
        other, _ = self.account("ad-attempt-other")
        self.exhaust_free_quota(user_id)
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "123456789"}):
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {}, token)[0], 400)
            status, attempt = self.call("/assistant/ad-reward", "POST", {"operation": "start", "provider": "vk"}, token)
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
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "123456789"}):
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {}, token)[0], 403)

    def test_production_never_offers_demo_rewarded_units(self):
        token, user_id = self.account("ad-demo-production")
        self.exhaust_free_quota(user_id)
        with patch.dict(os.environ, {"VERCEL_ENV": "production", "VK_REWARDED_SLOT_ID": "demo-rewarded-yandex"}):
            from backend.rewarded_ads import configured_unit
            self.assertEqual(configured_unit(), "")
        with patch("backend.rewarded_ads.configured_unit", return_value=""):
            self.assertFalse(self.call("/assistant/ad-reward", token=token)[1]["enabled"])
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {"operation": "start", "provider": "vk"}, token)[0], 503)

    def test_issued_reward_can_recover_when_placement_is_disabled(self):
        token, user_id = self.account("ad-recover-disabled")
        self.exhaust_free_quota(user_id)
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "123456789"}):
            status, attempt = self.call("/assistant/ad-reward", "POST", {"operation": "start", "provider": "vk"}, token)
            self.assertEqual(status, 200, attempt)
            self.assertGreaterEqual(attempt["expires_at"] - int(time.time()), 86390)
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": ""}):
            self.assertFalse(self.call("/assistant/ad-reward", token=token)[1]["enabled"])
            status, claim = self.call("/assistant/ad-reward", "POST", attempt, token)
            self.assertEqual(status, 200, claim)
            self.assertEqual(claim["granted"], ai_tokens.AD_REWARD_TOKENS)
            with self.mod.db() as con:
                con.execute("UPDATE assistant_ad_attempts SET expires_at=0 WHERE id=?", (attempt["attempt_id"],))
            status, replay = self.call("/assistant/ad-reward", "POST", attempt, token)
            self.assertEqual(status, 200, replay)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["quota"]["wallet"], ai_tokens.AD_REWARD_TOKENS)

    def test_production_refuses_client_only_reward_claims_even_if_approved(self):
        """No token issuance can depend on a forged client video callback."""
        import hashlib

        token, user_id = self.account("reward-unsafe-production")
        self.exhaust_free_quota(user_id)
        now = int(time.time())
        with self.mod.db() as con:
            con.execute(
                "INSERT INTO assistant_ad_attempts("
                "id,user_id,nonce_hash,status,created_at,expires_at) "
                "VALUES(?,?,?,'issued',?,?)",
                ("old-unverified-ad-attempt", user_id,
                 hashlib.sha256(b"forged-view").hexdigest(), now, now + 600),
            )
        with patch.dict(os.environ, {
            "VERCEL_ENV": "production", "VK_REWARDED_APPROVED": "1",
            "VK_REWARDED_SLOT_ID": "2106762",
        }):
            from backend.rewarded_ads import configured_unit

            self.assertEqual(configured_unit(), "")
            status, info = self.call("/assistant/ad-reward", token=token)
            self.assertEqual(status, 200, info)
            self.assertFalse(info["enabled"])
            self.assertEqual(
                self.call("/assistant/ad-reward", "POST", {
                    "operation": "start", "provider": "vk",
                }, token)[0], 503,
            )
            self.assertEqual(
                self.call("/assistant/ad-reward", "POST", {
                    "attempt_id": "old-unverified-ad-attempt",
                    "nonce": "forged-view",
                }, token)[0], 503,
            )
        with self.mod.db() as con:
            self.assertEqual(ai_tokens.wallet_balance(con, user_id), 0)
            self.assertEqual(con.execute(
                "SELECT status FROM assistant_ad_attempts WHERE id=?",
                ("old-unverified-ad-attempt",)
            ).fetchone()["status"], "issued")

    def test_pending_vk_moderation_hides_ad_despite_configured_slot(self):
        from backend.rewarded_ads import configured_unit

        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "2106762", "VK_REWARDED_APPROVED": "0"}):
            self.assertEqual(configured_unit(), "")
            token, user_id = self.account("ad-pending-moderation")
            self.exhaust_free_quota(user_id)
            status, offer = self.call("/assistant/ad-reward", token=token)
            self.assertEqual(status, 200, offer)
            self.assertFalse(offer["enabled"])
            self.assertFalse(offer["available"])
            self.assertEqual(offer["ad_unit_id"], "")
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {
                "operation": "start", "provider": "vk",
            }, token)[0], 503)
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "2106762", "VERCEL_ENV": "production"}):
            os.environ.pop("VK_REWARDED_APPROVED", None)
            self.assertEqual(configured_unit(), "")

    def test_guest_cannot_access_account_apis_or_create_ad_attempts(self):
        for path in ("/assistant/ad-reward", "/assistant", "/quotes", "/files", "/workspace"):
            with self.subTest(path=path):
                self.assertEqual(self.call(path)[0], 401)
        self.assertEqual(self.call("/assistant/ad-reward", "POST", {"operation": "start", "provider": "vk"})[0], 401)
        self.assertEqual(self.call("/quotes", "POST", {"title": "Guest", "items": []})[0], 401)

    def test_vk_slot_validation_and_old_app_requires_update(self):
        from backend.rewarded_ads import configured_unit
        for value in ("", "0", "-1", "2147483648", "demo-rewarded-yandex", "R-M-123", "1.0", "１２３"):
            with self.subTest(value=value), patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": value}):
                self.assertEqual(configured_unit(), "")
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "", "YANDEX_REWARDED_AD_UNIT_ID": "R-M-123"}):
            self.assertEqual(configured_unit(), "")
        token, user_id = self.account("ad-old-app")
        self.exhaust_free_quota(user_id)
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "123456789"}):
            self.assertEqual(self.call("/assistant/ad-reward", "POST", {"operation": "start"}, token)[0], 426)

    def test_concurrent_claims_credit_exactly_once(self):
        token, user_id = self.account("ad-concurrent")
        self.exhaust_free_quota(user_id)
        with patch.dict(os.environ, {"VK_REWARDED_SLOT_ID": "123456789"}):
            attempts = [self.call("/assistant/ad-reward", "POST", {"operation": "start", "provider": "vk"}, token)[1] for _ in range(2)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda attempt: self.call("/assistant/ad-reward", "POST", attempt, token), attempts * 2))
            self.assertEqual(sorted(status for status, _ in results), [200, 200, 409, 409])
            self.assertEqual(self.call("/assistant/ad-reward", token=token)[1]["quota"]["wallet"], ai_tokens.AD_REWARD_TOKENS)
            with self.mod.db() as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM assistant_ad_reward_credits WHERE user_id=?", (user_id,)).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
