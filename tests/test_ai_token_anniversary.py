"""Paid token allowances renew on successful payment anniversary, not UTC month 1."""
import datetime as dt
import sqlite3
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from backend import ai_tokens


def utc(year, month, day, hour=10):
    return int(dt.datetime(year, month, day, hour, tzinfo=dt.timezone.utc).timestamp())


class PaidTokenAnniversaryTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
          CREATE TABLE workspaces(id TEXT PRIMARY KEY,owner_id TEXT);
          CREATE TABLE payments(id TEXT PRIMARY KEY,user_id TEXT,plan TEXT,
            status TEXT,activated_at INTEGER,created_at INTEGER);
          CREATE TABLE billing_intents(payment_id TEXT,workspace_id TEXT,duration_days INTEGER);
          CREATE TABLE refunds(payment_id TEXT,status TEXT);
          CREATE TABLE rate_limits(key TEXT PRIMARY KEY,count INTEGER,started INTEGER);
          CREATE TABLE ai_token_wallets(user_id TEXT PRIMARY KEY,balance INTEGER);
          CREATE TABLE referral_rewards(inviter_id TEXT,bonus INTEGER,rewarded_at INTEGER,period TEXT);
        """)
        self.user = "paid-user"
        self.wid = str(uuid.uuid5(uuid.NAMESPACE_URL, "smetra-workspace:" + self.user))
        self.con.execute("INSERT INTO workspaces VALUES(?,?)", (self.wid, self.user))
        self.service = SimpleNamespace(con=self.con,wid=self.wid,user={"id": self.user})

    def tearDown(self):
        self.con.close()

    def pay(self, id, date, plan="pro_month", days=365, workspace=None):
        self.con.execute(
            "INSERT INTO payments VALUES(?,?,?,'succeeded',?,?)",
            (id, self.user, plan, date, date),
        )
        self.con.execute(
            "INSERT INTO billing_intents VALUES(?,?,?)",
            (id, self.wid if workspace is None else workspace, days),
        )

    def balance_at(self, moment, tier="pro_solo"):
        with patch.object(ai_tokens, "stamp", return_value=moment), \
             patch.object(ai_tokens, "tier_of", return_value=tier), \
             patch.object(ai_tokens, "absorb_legacy_credits", return_value=None):
            return ai_tokens.balance(self.service)

    def test_paid_resets_on_purchase_day_not_first(self):
        activated = utc(2026, 10, 15, 14)
        self.pay("p1", activated)
        before = self.balance_at(utc(2026, 10, 27))
        self.assertEqual(before["resets_at"], utc(2026, 11, 15, 14))
        self.assertNotEqual(before["resets_at"], utc(2026, 11, 1, 0))
        self.con.execute("INSERT INTO rate_limits VALUES(?,?,?)", (before["key"], 7500, activated))
        still_before = self.balance_at(utc(2026, 11, 15, 13))
        self.assertEqual(still_before["monthly_used"], 7500)
        after = self.balance_at(utc(2026, 11, 15, 14))
        self.assertEqual(after["monthly_used"], 0)
        self.assertEqual(after["resets_at"], utc(2026, 12, 15, 14))
        self.assertNotEqual(before["key"], after["key"])
        self.assertEqual(after["wallet"], 0)

    def test_month_end_and_leap_anniversaries(self):
        jan31 = utc(2025, 1, 31)
        self.assertEqual(ai_tokens._anniversary_window(jan31, utc(2025, 2, 27)),
                         (jan31, utc(2025, 2, 28)))
        self.assertEqual(ai_tokens._anniversary_window(jan31, utc(2025, 2, 28)),
                         (utc(2025, 2, 28), utc(2025, 3, 31)))
        leap = utc(2024, 1, 31)
        self.assertEqual(ai_tokens._anniversary_window(leap, utc(2024, 2, 29)),
                         (utc(2024, 2, 29), utc(2024, 3, 31)))

    def test_same_tier_renewal_does_not_refill_early(self):
        anchor = utc(2026, 1, 12)
        self.pay("p1", anchor, days=365)
        original = self.balance_at(utc(2026, 3, 5))
        self.pay("p2", utc(2026, 3, 6), days=365)
        renewed = self.balance_at(utc(2026, 3, 7))
        self.assertEqual(renewed["key"], original["key"])
        self.assertEqual(renewed["resets_at"], original["resets_at"])

    def test_lapsed_subscription_restarts_anniversary(self):
        self.pay("p1", utc(2026, 1, 12), days=30)
        self.pay("p2", utc(2026, 6, 18), days=365)
        next_period = self.balance_at(utc(2026, 7, 1))
        self.assertEqual(next_period["resets_at"], utc(2026, 7, 18))

    def test_refund_and_wrong_workspace_cannot_anchor_entitlement(self):
        self.pay("p1", utc(2026, 1, 15))
        self.con.execute("INSERT INTO refunds VALUES('p1','succeeded')")
        self.assertIsNone(ai_tokens._paid_activation(self.service, "pro_solo", utc(2026, 2, 1)))
        self.pay("p2", utc(2026, 2, 19), days=365, workspace="another-workspace")
        self.assertIsNone(ai_tokens._paid_activation(self.service, "pro_solo", utc(2026, 3, 1)))
        self.pay("p3", utc(2026, 3, 21), days=365)
        self.assertEqual(ai_tokens._paid_activation(self.service, "pro_solo", utc(2026, 4, 1)),
                         utc(2026, 3, 21))

    def test_free_still_resets_first_and_wallet_survives(self):
        self.con.execute("INSERT INTO ai_token_wallets VALUES(?,?)", (self.user, 34000))
        current = self.balance_at(utc(2026, 10, 27), tier="starter")
        self.assertEqual(current["resets_at"], utc(2026, 11, 1, 0))
        self.assertEqual(current["wallet"], 34000)
