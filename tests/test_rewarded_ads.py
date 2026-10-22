import os
import sqlite3
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import assistant, business
from backend.business import DomainError


class _Handler:
    def throttle(self, *_args, **_kwargs):
        return None


class RewardedAdSecurityTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {"REWARDED_ADS_REQUIRED": "1"})
        self.env_patch.start()
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
        self.user = self.con.execute("SELECT * FROM users WHERE id='ad-user'").fetchone()
        self.service = SimpleNamespace(
            con=self.con,
            user=self.user,
            wid="not-a-workspace",
            h=_Handler(),
        )

    def tearDown(self):
        self.con.close()
        self.env_patch.stop()

    def test_client_nonce_does_not_mint_reward_credits(self):
        for action in (["rewarded-ad", "start"], ["rewarded-ad", "complete"]):
            with self.assertRaises(DomainError) as ctx:
                assistant.route(
                    self.service,
                    "POST",
                    action,
                    {"attempt_id": "attacker-controlled", "nonce": "attacker-controlled"},
                )
            self.assertEqual(ctx.exception.status, 503)
            self.assertIn("серверная проверка", ctx.exception.message.lower())
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM assistant_ad_attempts").fetchone()[0], 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM assistant_ad_reward_credits").fetchone()[0], 0)

    def test_paid_workspace_cannot_claim_ad_rewards(self):
        now = int(time.time())
        wid = business.ensure_workspace(self.con, self.user)
        self.con.execute(
            "UPDATE workspaces SET plan='pro_team',subscription_status='active',entitlement_until=?,seat_limit=5 WHERE id=?",
            (now + 86400, wid),
        )
        self.service.wid = wid
        with self.assertRaises(DomainError) as ctx:
            assistant.route(self.service, "POST", ["rewarded-ad", "start"], {})
        self.assertEqual(ctx.exception.status, 503)


if __name__ == "__main__":
    unittest.main()
