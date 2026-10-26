"""Token packs: server prices, one credit per confirmed payment, refund takes back the rest."""
import os
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import ai_tokens, business, token_packs
from backend.app import Handler
from backend.business import DomainError


class TokenPackPriceTests(unittest.TestCase):
    def test_graduated_price_never_drops_with_more_tokens(self):
        prices = [token_packs.price(n) for n in range(1, token_packs.MAX_MILLIONS + 1)]
        self.assertEqual(prices[0], 24900)
        self.assertTrue(all(b > a for a, b in zip(prices, prices[1:])))
        # Cheapest band still covers the paid model's cost (~70 ₽ per million) with margin.
        self.assertGreaterEqual(min(rate for _, rate in token_packs.BANDS), 2 * 7000)
        for bad in (0, 51, 2.5, "3", True, None):
            with self.subTest(bad=bad), self.assertRaises(DomainError):
                token_packs.price(bad)

    def test_codes_round_trip_and_reject_other_products(self):
        self.assertEqual(token_packs.millions_of(token_packs.code(10)), 10)
        for plan in ("pro_month", "tokens_0m", "tokens_51m", "tokens_10", "tokens_010m", None):
            self.assertIsNone(token_packs.millions_of(plan))
        offer = token_packs.offer()
        self.assertEqual([p["millions"] for p in offer["packs"]], [1, 3, 10, 25])
        self.assertTrue(all(p["amount_kopecks"] == token_packs.price(p["millions"]) for p in offer["packs"]))


class TokenPackPaymentTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:", isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript((Path(__file__).parents[1] / "backend/schema.sql").read_text())
        business.migrate(self.con)
        now = business.stamp()
        self.con.execute(
            "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,?,?,?)",
            ("buyer", "buyer@test.invalid", "unused", "Test", now, now),
        )
        self.user = self.con.execute("SELECT * FROM users WHERE id='buyer'").fetchone()

    def tearDown(self):
        self.con.close()

    def pay(self, millions):
        amount = token_packs.price(millions)
        plan = token_packs.code(millions)
        self.con.execute(
            "INSERT INTO billing_intents(id,user_id,request_key,plan,amount_kopecks,duration_days,variant,source,is_test,created_at,bonus_ai_messages,workspace_id) "
            "VALUES('intent','buyer','key-0000000000000001',?,?,1,'tokens','pricing_page',0,?,0,?)",
            (plan, amount, business.stamp(), business.ensure_workspace(self.con, self.user)),
        )
        self.con.execute(
            "INSERT INTO payments(id,user_id,provider_id,plan,amount_kopecks,status,idempotency_key,confirmation_url,created_at) "
            "VALUES('pay','buyer','provider-1',?,?,'pending','key-0000000000000001','https://pay.test',?)",
            (plan, amount, business.stamp()),
        )
        self.con.execute("UPDATE billing_intents SET payment_id='pay' WHERE id='intent'")
        local = self.con.execute("SELECT * FROM payments WHERE id='pay'").fetchone()
        remote = {"id": "provider-1", "amount": {"value": f"{amount / 100:.2f}", "currency": "RUB"},
                  "metadata": {"user_id": "buyer", "plan": plan}, "status": "succeeded", "paid": True,
                  "recipient": {"account_id": "test-shop"}, "test": False}
        env = {"YOOKASSA_MODE": "live", "YOOKASSA_MERCHANT_TYPE": "self_employed", "YOOKASSA_SHOP_ID": "test-shop", "YOOKASSA_SECRET_KEY": "fake"}
        handler = object.__new__(Handler)
        with patch.dict(os.environ, env), patch("backend.mytracker.track_custom_event", return_value=True):
            handler.apply_payment(self.con, local, remote)
            handler.apply_payment(self.con, local, remote)
        return handler, remote, amount

    def test_confirmed_payment_credits_once_and_keeps_subscription(self):
        self.pay(3)
        self.assertEqual(ai_tokens.wallet_balance(self.con, "buyer"), 3 * token_packs.MILLION)
        user = self.con.execute("SELECT plan,entitlement_until FROM users WHERE id='buyer'").fetchone()
        self.assertEqual((user["plan"], user["entitlement_until"] or 0), ("free", 0))

    def test_refund_takes_back_unspent_tokens_only(self):
        handler, remote, amount = self.pay(1)
        service = SimpleNamespace(con=self.con, user=self.user)
        self.con.execute("INSERT INTO rate_limits(key,count,started) VALUES(?,?,?)",
                         (ai_tokens.month_key("buyer"), 10**9, business.stamp()))
        ai_tokens.charge(service, 400_000)
        with patch.dict(os.environ, {"YOOKASSA_MODE": "live"}):
            handler.apply_refund(self.con, {"id": "refund-1", "payment_id": "provider-1", "status": "succeeded",
                                            "amount": remote["amount"]})
        self.assertEqual(ai_tokens.wallet_balance(self.con, "buyer"), 0)


if __name__ == "__main__":
    unittest.main()
