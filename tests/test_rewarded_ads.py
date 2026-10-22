import sqlite3
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend import assistant, business
from backend.business import DomainError


class _Handler:
    def throttle(self, *_args, **_kwargs):
        return None


class RewardedAdTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:", isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript((Path(__file__).parents[1] / "backend" / "schema.sql").read_text())
        business.migrate(self.con)
        now = int(time.time())
        self.con.execute(
            "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,?,?,?)",
            ("ad-user", "ad-user@test.invalid", "unused", "Ad user", now, now),
        )
        user = self.con.execute("SELECT * FROM users WHERE id='ad-user'").fetchone()
        self.service = SimpleNamespace(
            con=self.con,
            user=user,
            wid="not-a-workspace",
            h=_Handler(),
        )

    def tearDown(self):
        self.con.close()

    def test_free_user_has_no_unearned_allowance(self):
        quota = assistant.quota(self.service)
        self.assertEqual(quota["plan"], "free")
        self.assertEqual(quota["base_limit"], 0)
        self.assertEqual(quota["remaining"], 0)
        with self.assertRaises(DomainError):
            assistant.reserve(self.service)

    def test_single_use_ad_reward_issues_three_credits_and_replay_is_idempotent(self):
        status, challenge = assistant.route(
            self.service, "POST", ["rewarded-ad", "start"], {}
        )
        self.assertEqual(status, 201)
        self.assertEqual(challenge["reward_tokens"], 3)

        payload = {"attempt_id": challenge["attempt_id"], "nonce": challenge["nonce"]}
        status, granted = assistant.route(
            self.service, "POST", ["rewarded-ad", "complete"], payload
        )
        self.assertEqual(status, 200)
        self.assertFalse(granted["duplicate"])
        self.assertEqual(granted["awarded_tokens"], 3)
        self.assertEqual(assistant.quota(self.service)["remaining"], 3)

        status, replay = assistant.route(
            self.service, "POST", ["rewarded-ad", "complete"], payload
        )
        self.assertEqual(status, 200)
        self.assertTrue(replay["duplicate"])
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM assistant_ad_reward_credits").fetchone()[0],
            1,
        )
        self.assertEqual(assistant.quota(self.service)["remaining"], 3)

    def test_nonce_mismatch_cannot_mint_credits(self):
        _, challenge = assistant.route(
            self.service, "POST", ["rewarded-ad", "start"], {}
        )
        with self.assertRaises(DomainError):
            assistant.route(
                self.service,
                "POST",
                ["rewarded-ad", "complete"],
                {"attempt_id": challenge["attempt_id"], "nonce": "not-the-nonce"},
            )
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM assistant_ad_reward_credits").fetchone()[0],
            0,
        )

    def test_each_reserved_ad_request_consumes_one_and_release_restores_it(self):
        _, challenge = assistant.route(
            self.service, "POST", ["rewarded-ad", "start"], {}
        )
        assistant.route(
            self.service, "POST", ["rewarded-ad", "complete"],
            {"attempt_id": challenge["attempt_id"], "nonce": challenge["nonce"]},
        )
        reservation = assistant.reserve(self.service)
        self.assertEqual(reservation["ad_reward_id"] is not None, True)
        self.assertEqual(assistant.quota(self.service)["remaining"], 2)
        assistant.release(self.service, reservation)
        self.assertEqual(assistant.quota(self.service)["remaining"], 3)
        for _ in range(3):
            assistant.reserve(self.service)
        self.assertEqual(assistant.quota(self.service)["remaining"], 0)
        with self.assertRaises(DomainError):
            assistant.reserve(self.service)

    def test_paid_workspace_cannot_claim_ad_rewards(self):
        now = int(time.time())
        wid = business.ensure_workspace(self.con, self.service.user)
        self.con.execute(
            "UPDATE workspaces SET plan='pro_team',subscription_status='active',entitlement_until=?,seat_limit=6 WHERE id=?",
            (now + 86400, wid),
        )
        self.service.wid = wid
        with self.assertRaises(DomainError):
            assistant.route(self.service, "POST", ["rewarded-ad", "start"], {})


if __name__ == "__main__":
    unittest.main()
