import os
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import business, revenue
from backend.plan_catalog import PUBLIC_PLAN_CODES


class SubscriptionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:", isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript((Path(__file__).parents[1] / "backend" / "schema.sql").read_text())
        business.migrate(self.con)
        now = revenue.now()
        self.con.execute(
            "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,?,?,?)",
            ("catalog-user", "catalog-user@test.invalid", "unused", "Catalog", now, now),
        )
        self.user = self.con.execute("SELECT * FROM users WHERE id='catalog-user'").fetchone()

    def tearDown(self):
        self.con.close()

    def test_fixed_catalog_contains_expected_tiers_and_prices(self):
        offer = revenue.pricing(self.con, self.user)
        self.assertEqual(
            PUBLIC_PLAN_CODES,
            frozenset({"pro_month", "pro_year", "pro_plus_month", "pro_team_month", "pro_team_year"}),
        )
        self.assertEqual(
            {code: item["amount_kopecks"] for code, item in offer["plans"].items()},
            {
                "pro_month": 49000,
                "pro_year": 490000,
                "pro_plus_month": 69000,
                "pro_team_month": 399000,
                "pro_team_year": 3990000,
            },
        )
        self.assertEqual(offer["annual_saving_kopecks"], 98000)
        self.assertEqual(offer["team_annual_saving_kopecks"], 798000)
        self.assertFalse(any("token" in code for code in offer["plans"]))

    def test_environment_overrides_cannot_change_published_prices(self):
        env = {
            "PRICING_EXPERIMENT_ID": "old-experiment",
            "PRICING_VARIANTS_JSON": '{"cheap":{"month":29900,"year":239000}}',
            "PRO_MONTH_PRICE_KOPECKS": "69900",
            "PRO_YEAR_PRICE_KOPECKS": "599000",
            "PRO_TEAM_MONTH_PRICE_KOPECKS": "249000",
        }
        with patch.dict(os.environ, env):
            offer = revenue.pricing(self.con, self.user)
            self.assertEqual(offer["plans"]["pro_month"]["amount_kopecks"], 49000)
            self.assertEqual(offer["plans"]["pro_year"]["amount_kopecks"], 490000)
            self.assertEqual(offer["plans"]["pro_team_month"]["amount_kopecks"], 399000)

    def test_microtransactions_are_not_new_checkout_products(self):
        for code in ("lead_tokens_150", "smart_supplier_month"):
            with self.assertRaises(ValueError):
                revenue.prepare_intent(
                    self.con, self.user, "legacy-key-" + code, code, "pricing_page", False
                )

    def test_team_annual_intent_uses_annual_price_and_duration(self):
        wid = business.ensure_workspace(self.con, self.user)
        intent = revenue.prepare_intent(
            self.con, self.user, "team-annual-checkout-key", "pro_team_year",
            "pricing_page", False, expected_amount=3990000, workspace_id=wid,
        )
        self.assertEqual(intent["amount_kopecks"], 3990000)
        self.assertEqual(intent["duration_days"], 366)
        self.assertEqual(intent["workspace_id"], wid)

    def test_pro_plus_intent_uses_fixed_monthly_price(self):
        intent = revenue.prepare_intent(
            self.con, self.user, "plus-month-checkout-key", "pro_plus_month",
            "pricing_page", False, expected_amount=69000,
        )
        self.assertEqual(intent["amount_kopecks"], 69000)
        self.assertEqual(intent["duration_days"], 31)


if __name__ == "__main__":
    unittest.main()
