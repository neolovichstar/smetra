"""Partner attribution/commission isolation and untrusted catalog validation."""
import os
import sqlite3
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import business, partner_platform as partner, partner_integrations as integration, revenue
from backend.app import Handler


class PartnerPlatformTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:", isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript((Path(__file__).parents[1] / "backend/schema.sql").read_text())
        business.migrate(self.con)
        self.partner = partner.create_partner(self.con, {
            "code": "materials-market", "name": "Materials",
            "allowed_host": "partner.shop", "commission_bps": 2000, "term_days": 365,
        })
        self.other = partner.create_partner(self.con, {
            "code": "other-store", "name": "Other", "allowed_host": "other.shop",
            "commission_bps": 1000, "term_days": 365,
        })

    def tearDown(self):
        self.con.close()

    def _account(self, user_id, created_at=None):
        self.con.execute(
            "INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) "
            "VALUES(?,?,?,?,?,?)",
            (user_id, user_id + "@test.invalid", "unused", "Customer",
             created_at or int(time.time()), int(time.time())),
        )
        return self.con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def _purchase(self, user, key="paid_123456789123", plan="pro_month", test=False):
        intent = revenue.prepare_intent(self.con, user, key, plan, "pricing_page", test)
        remote = {
            "id": "provider-" + key, "test": test, "paid": True, "status": "succeeded",
            "recipient": {"account_id": "test-shop"},
            "amount": {"currency": "RUB", "value": f"{intent['amount_kopecks'] / 100:.2f}"},
            "metadata": {"user_id": user["id"], "plan": plan},
            "confirmation": {"confirmation_url": "https://pay.test.invalid"},
        }
        local, _ = revenue.persist_checkout(self.con, user, key, plan, intent, remote)
        env = {"YOOKASSA_MODE": "test" if test else "live", "YOOKASSA_MERCHANT_TYPE": "self_employed",
               "YOOKASSA_SHOP_ID": "test-shop", "YOOKASSA_SECRET_KEY": "fake"}
        with patch.dict(os.environ, env), patch("backend.mytracker.track_custom_event"):
            handler = object.__new__(Handler)
            handler.apply_payment(self.con, local, remote)
            handler.apply_payment(self.con, local, remote)
        return local, remote

    def test_token_hash_only_and_partner_isolation(self):
        self.assertIsNone(self.con.execute(
            "SELECT id FROM partner_api_tokens WHERE token_hash=?", (self.partner["api_key"],)
        ).fetchone())
        p = partner.auth_partner(self.con, "Partner " + self.partner["api_key"])
        self.assertEqual(p["id"], self.partner["id"])
        self.assertEqual(partner.summary(self.con, p)["clicks_30d"], 0)
        with self.assertRaises(partner.PartnerError):
            partner.auth_partner(self.con, "Bearer " + self.partner["api_key"])
        other = partner.auth_partner(self.con, "Partner " + self.other["api_key"])
        self.assertNotEqual(other["id"], p["id"])

    def test_first_touch_payment_idempotency_and_refund(self):
        token = partner.begin_visit(self.con, "materials-market")
        user = self._account("buyer")
        self.assertTrue(partner.capture(self.con, user, partner.COOKIE_NAME + "=" + token))
        self.assertFalse(partner.capture(self.con, user, partner.COOKIE_NAME + "=" + token))
        # Another partner cannot take over an already attributed account.
        token2 = partner.begin_visit(self.con, "other-store")
        self.assertFalse(partner.capture(self.con, user, partner.COOKIE_NAME + "=" + token2))
        local, remote = self._purchase(user)
        rate = self.con.execute("SELECT rate_bps FROM partner_attributions WHERE user_id=?", (user["id"],)).fetchone()[0]
        self.assertEqual(rate, 2000)
        commission = self.con.execute("SELECT * FROM partner_commissions WHERE payment_id=?", (local["id"],)).fetchone()
        self.assertEqual(commission["commission_kopecks"], local["amount_kopecks"] * 20 // 100)
        self.assertEqual(self.con.execute("SELECT count(*) FROM partner_commissions").fetchone()[0], 1)
        other = partner.auth_partner(self.con, "Partner " + self.other["api_key"])
        self.assertEqual(partner.summary(self.con, other)["conversions"], 0)
        self.assertEqual(partner.summary(self.con, other)["earned_kopecks"], 0)
        handler = object.__new__(Handler)
        handler.apply_refund(self.con, {
            "id": "refund-one", "payment_id": remote["id"], "status": "succeeded",
            "amount": remote["amount"],
        })
        self.assertEqual(self.con.execute(
            "SELECT status FROM partner_commissions WHERE payment_id=?", (local["id"],)
        ).fetchone()[0], "reversed")
        self.assertEqual(partner.summary(self.con, partner.auth_partner(self.con, "Partner " + self.partner["api_key"]))["earned_kopecks"], 0)

    def test_no_commissions_for_test_payments_or_existing_users(self):
        token = partner.begin_visit(self.con, "materials-market")
        with patch("backend.partner_platform._now", return_value=int(time.time()) - 15 * 86400):
            old = self._account("old", int(time.time()) - 15 * 86400)
            self.assertFalse(partner.capture(self.con, old, partner.COOKIE_NAME + "=" + token))
        person = self._account("test-buyer")
        self.assertTrue(partner.capture(self.con, person, partner.COOKIE_NAME + "=" + token))
        self._purchase(person, key="test_purchase_123456", test=True)
        self.assertEqual(self.con.execute("SELECT count(*) FROM partner_commissions").fetchone()[0], 0)

    def test_product_url_validation_and_tenant_scoping(self):
        p = partner.auth_partner(self.con, "Partner " + self.partner["api_key"])
        with self.assertRaises(partner.PartnerError):
            partner.ingest_products(self.con, p, {"products": [
                {"sku": "M1", "name": "Блок", "price_kopecks": 100,
                 "url": "https://untrusted.example/item", "available": True}
            ]})
        self.assertEqual(partner.ingest_products(self.con, p, {"products": [
            {"sku": "M1", "name": "Газобетонный блок", "price_kopecks": 12000,
             "url": "https://partner.shop/products/1", "available": True}
        ]})["accepted"], 1)
        self.assertEqual(len(partner.offers(self.con, "блок")["offers"]), 0,
                         "Unverified vendors cannot publish links to the estimate buyer")
        integration.begin_verification(self.con, p, "dns")
        with patch("backend.partner_integrations._verify_dns", return_value=True):
            self.assertEqual(integration.verify_domain(self.con, p)["status"], "verified")
        self.assertEqual(len(partner.offers(self.con, "блок")["offers"]), 1)
        pid = partner.offers(self.con, "блок")["offers"][0]["id"]
        buyer = self._account("another-buyer")
        self.assertEqual(partner.outbound(self.con, buyer, pid), "https://partner.shop/products/1")
        self.assertEqual(self.con.execute("SELECT count(*) FROM partner_outbound_clicks").fetchone()[0], 1)
        other = partner.auth_partner(self.con, "Partner " + self.other["api_key"])
        with self.assertRaises(partner.PartnerError):
            partner.ingest_products(self.con, other, {"products": [
                {"sku": "M2", "name": "Блок", "price_kopecks": 100, "url": "https://partner.shop/items/2"}
            ]})


    def test_domain_verification_is_partner_scoped_and_never_follows_remote_links(self):
        p = partner.auth_partner(self.con, "Partner " + self.partner["api_key"])
        other = partner.auth_partner(self.con, "Partner " + self.other["api_key"])
        challenge = integration.begin_verification(self.con, p, "meta")
        self.assertEqual(challenge["status"], "pending")
        self.assertEqual(challenge["domain"], "partner.shop")
        self.assertEqual(integration.domain_status(self.con, other)["status"], "not_started")
        with patch("backend.partner_integrations._verify_meta", return_value=False):
            self.assertEqual(integration.verify_domain(self.con, p)["status"], "pending")
        with patch("backend.partner_integrations._verify_meta", return_value=True):
            self.assertEqual(integration.verify_domain(self.con, p)["status"], "verified")
        self.assertEqual(integration.begin_verification(self.con, p, "dns")["status"], "verified")
        checker = integration._MetaChecker(challenge["token"])
        checker.feed('<html><head><meta name="smetra-domain-verification" content="' + challenge["token"] + '"></head>')
        self.assertTrue(checker.matched)
        checker2 = integration._MetaChecker(challenge["token"])
        checker2.feed('<meta name="smetra-domain-verification" content="fake">')
        self.assertFalse(checker2.matched)

    def test_self_reported_events_are_deduplicated_and_not_payment_proof(self):
        p = partner.auth_partner(self.con, "Partner " + self.partner["api_key"])
        with self.assertRaises(partner.PartnerError):
            integration.report_event(self.con, p, {
                "event_key": "material-order-id-01", "event_type": "material_order_reported",
                "amount_kopecks": 120000,
            })
        integration.begin_verification(self.con, p, "dns")
        with patch("backend.partner_integrations._verify_dns", return_value=True):
            integration.verify_domain(self.con, p)
        order = {"event_key": "material-order-id-01", "event_type": "material_order_reported",
                 "amount_kopecks": 120000}
        self.assertFalse(integration.report_event(self.con, p, order)["trusted"])
        integration.report_event(self.con, p, order)
        with self.assertRaises(partner.PartnerError) as conflicting:
            integration.report_event(self.con, p, {**order, "amount_kopecks": 220000})
        self.assertEqual(conflicting.exception.status, 409)
        stat = integration.analytics(self.con, p, 7)
        self.assertEqual(stat["merchant_reported"]["material_order_reported"]["count"], 1)
        self.assertEqual(stat["merchant_reported"]["material_order_reported"]["amount_kopecks"], 120000)
        self.assertEqual(stat["verified_subscription_payments"]["payments"], 0)
        self.assertFalse(stat["payouts_enabled"])
        with self.assertRaises(partner.PartnerError):
            integration.report_event(self.con, p, {**order, "email": "someone@example.com"})

    def test_console_access_tokens_expire_and_revoke(self):
        login = partner.new_console_session(self.con, "Partner " + self.partner["api_key"])
        header = "PartnerSession " + login["session_token"]
        self.assertEqual(partner.auth_console(self.con, header)["code"], "materials-market")
        self.assertFalse(self.con.execute(
            "SELECT id FROM partner_console_sessions WHERE session_hash=?",
            (login["session_token"],)
        ).fetchone())
        self.assertTrue(partner.revoke_console_session(self.con, header))
        with self.assertRaises(partner.PartnerError):
            partner.auth_console(self.con, header)
        new = partner.new_console_session(self.con, "Partner " + self.partner["api_key"])
        with patch("backend.partner_platform._now", return_value=int(time.time()) + 7200):
            with self.assertRaises(partner.PartnerError):
                partner.auth_console(self.con, "PartnerSession " + new["session_token"])

    def test_admin_key_rotation_invalidates_sessions_and_old_keys(self):
        original = partner.auth_partner(self.con, "Partner " + self.partner["api_key"])
        issued = partner.new_console_session(self.con, "Partner " + self.partner["api_key"])
        rotated = partner.rotate_api_key(self.con, original["id"])
        self.assertEqual(rotated["partner"], "materials-market")
        self.assertNotEqual(rotated["api_key"], self.partner["api_key"])
        with self.assertRaises(partner.PartnerError):
            partner.auth_partner(self.con, "Partner " + self.partner["api_key"])
        with self.assertRaises(partner.PartnerError):
            partner.auth_console(self.con, "PartnerSession " + issued["session_token"])
        self.assertEqual(partner.auth_partner(self.con, "Partner " + rotated["api_key"])["id"], original["id"])

    def test_partner_read_models_are_scoped_and_paged(self):
        main = partner.auth_partner(self.con, "Partner " + self.partner["api_key"])
        other = partner.auth_partner(self.con, "Partner " + self.other["api_key"])
        self.assertFalse(partner.partner_profile(self.con, main)["payouts_enabled"])
        self.assertEqual(partner.partner_profile(self.con, main)["domain_status"], "not_started")
        for i in range(3):
            partner.ingest_products(self.con, main, {"products": [{
                "sku": f"SKU-{i:03d}", "name": "Блок", "price_kopecks": i + 100,
                "url": f"https://partner.shop/items/{i}", "available": True,
            }]})
        partner.ingest_products(self.con, other, {"products": [{
            "sku": "PRIVATE", "name": "Private", "price_kopecks": 11,
            "url": "https://other.shop/private", "available": True,
        }]})
        first = partner.catalog_page(self.con, main, 2)
        self.assertEqual(len(first["items"]), 2)
        second = partner.catalog_page(self.con, main, 2, first["next_cursor"])
        self.assertEqual([x["sku"] for x in second["items"]], ["SKU-002"])
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(len(partner.catalog_page(self.con, other)["items"]), 1)
        self.assertEqual(partner.commission_page(self.con, main)["items"], [])
        for invalid in (-1, 0, 101, "5", True):
            with self.assertRaises(partner.PartnerError):
                partner.catalog_page(self.con, main, invalid)
        with self.assertRaises(partner.PartnerError):
            partner.commission_page(self.con, main, cursor="invalid")

    def test_commission_receipts_never_expose_customer_data(self):
        main = partner.auth_partner(self.con, "Partner " + self.partner["api_key"])
        token = partner.begin_visit(self.con, "materials-market")
        user = self._account("receipts-buyer")
        self.assertTrue(partner.capture(self.con, user, partner.COOKIE_NAME + "=" + token))
        self._purchase(user, key="receipts_paid_1234567")
        response = partner.commission_page(self.con, main)
        self.assertEqual(len(response["items"]), 1)
        receipt = response["items"][0]
        self.assertIn(receipt["status"], ("held", "cleared_unpaid"))
        for forbidden in ("user_id", "email", "payment_id", "provider_id"):
            self.assertNotIn(forbidden, receipt)
        self.assertEqual(
            partner.commission_page(
                self.con, partner.auth_partner(self.con, "Partner " + self.other["api_key"])
            )["items"], []
        )

    def test_admin_pause_revokes_console_and_blocks_referrals(self):
        p = partner.auth_partner(self.con, "Partner " + self.partner["api_key"])
        login = partner.new_console_session(self.con, "Partner " + self.partner["api_key"])
        self.assertFalse(partner.set_partner_active(self.con, p["id"], False)["active"])
        with self.assertRaises(partner.PartnerError):
            partner.auth_console(self.con, "PartnerSession " + login["session_token"])
        with self.assertRaises(partner.PartnerError):
            partner.begin_visit(self.con, p["code"])
        self.assertTrue(partner.set_partner_active(self.con, p["id"], True)["active"])
        self.assertEqual(
            partner.auth_partner(self.con, "Partner " + self.partner["api_key"])["id"], p["id"]
        )
        with self.assertRaises(partner.PartnerError):
            partner.set_partner_active(self.con, p["id"], "true")

    def test_reconcile_is_idempotent_uses_payment_date_and_skips_refunds(self):
        token = partner.begin_visit(self.con, "materials-market")
        buyer = self._account("reconcile-buyer")
        self.assertTrue(partner.capture(self.con, buyer, partner.COOKIE_NAME + "=" + token))
        payment, remote = self._purchase(buyer, key="reconcile_payment_123456")
        historic = int(time.time()) - 86400
        self.con.execute("UPDATE payments SET activated_at=? WHERE id=?",
                         (historic, payment["id"]))
        self.con.execute("DELETE FROM partner_commissions WHERE payment_id=?", (payment["id"],))
        self.con.execute("UPDATE partner_attributions SET first_paid_at=NULL WHERE user_id=?",
                         (buyer["id"],))
        repaired = partner.reconcile_confirmed_payments(self.con)
        self.assertEqual(repaired["created"], 1)
        self.assertEqual(self.con.execute(
            "SELECT created_at FROM partner_commissions WHERE payment_id=?",
            (payment["id"],)).fetchone()[0], historic)
        self.assertEqual(partner.reconcile_confirmed_payments(self.con)["created"], 0)
        handler = object.__new__(Handler)
        handler.apply_refund(self.con, {"id": "reconcile-refund",
                                         "payment_id": remote["id"],
                                         "status": "succeeded",
                                         "amount": remote["amount"]})
        self.con.execute("DELETE FROM partner_commissions WHERE payment_id=?", (payment["id"],))
        self.assertEqual(partner.reconcile_confirmed_payments(self.con)["created"], 0)
        with self.assertRaises(partner.PartnerError):
            partner.reconcile_confirmed_payments(self.con, limit=101)

if __name__ == "__main__":
    unittest.main()
