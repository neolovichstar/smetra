"""End-to-end plan/tenant/payment boundaries on isolated SQLite fixtures."""
import json
import os
import secrets
import unittest
from unittest.mock import patch

from tests import test_business
from backend import revenue, object_chats


class EcosystemTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    def account(self, name):
        import hashlib
        token, user_id = secrets.token_urlsafe(32), self.mod.uid()
        with self.mod.db() as con:
            con.execute("INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,?,?,?)",
                        (user_id, name+"@test.invalid", "unused", name, self.mod.now(), self.mod.now()))
            con.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                        (self.mod.uid(), user_id, hashlib.sha256(token.encode()).hexdigest(), self.mod.now()+3600))
        return token, user_id
    call = test_business.BusinessFlows.call

    def plan(self, token, code="team_month"):
        wid = self.call("/workspace", token=token)[1]["workspace"]["id"]
        with self.mod.db() as con:
            con.execute("UPDATE workspaces SET plan=?,subscription_status='active',entitlement_until=?,seat_limit=5 WHERE id=?",
                        (code, self.mod.now()+86400, wid))
        return wid

    def test_four_products_and_server_prices(self):
        token, _ = self.account("eco-catalog")
        status, data = self.call("/billing", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(set(data["pricing"]["catalog"]), {"starter", "pro_solo", "pro_plus", "team"})
        self.assertEqual(data["plans"]["pro_plus_month"], 149000)
        self.assertEqual(data["plans"]["team_year"], 6990000)
        self.assertNotIn("business_month", data["plans"])

    def test_free_and_solo_cannot_add_staff_and_team_is_five_seats(self):
        owner, _ = self.account("eco-owner")
        colleagues = [self.account("eco-member-"+str(i)) for i in range(5)]
        payload = {"email": "eco-member-0@test.invalid", "role": "member"}
        self.assertEqual(self.call("/workspace/members", "POST", payload, owner)[0], 402)
        self.plan(owner, "pro_month")
        self.assertEqual(self.call("/workspace/members", "POST", payload, owner)[0], 402)
        wid = self.plan(owner)
        for i in range(4):
            payload["email"] = "eco-member-"+str(i)+"@test.invalid"
            self.assertEqual(self.call("/workspace/members", "POST", payload, owner)[0], 200)
        payload["email"] = "eco-member-4@test.invalid"
        self.assertEqual(self.call("/workspace/members", "POST", payload, owner)[0], 409)
        # Changing a role on an existing seat must still work when all seats are taken.
        payload.update(email="eco-member-0@test.invalid", role="manager")
        self.assertEqual(self.call("/workspace/members", "POST", payload, owner)[0], 200)
        self.assertEqual(self.call("/workspace", token=colleagues[0][0], workspace=wid)[1]["entitlements"]["tier"], "team")

    def test_chat_idempotency_sequence_and_tenant_isolation(self):
        owner, _ = self.account("eco-chat-owner")
        other, _ = self.account("eco-chat-other")
        obj = self.call("/construction/objects", "POST", {"name": "Объект"}, owner)[1]["object"]
        self.assertEqual(self.call("/object-chats", "POST", {"object_id": obj["id"]}, owner)[0], 402)
        self.plan(owner)
        status, created = self.call("/object-chats", "POST", {"object_id": obj["id"]}, owner)
        self.assertEqual(status, 200, created)
        thread = created["thread"]["id"]
        self.assertEqual(self.call("/object-chats", "POST", {"object_id": obj["id"]}, owner)[1]["thread"]["id"], thread)
        path = "/object-chats/"+thread+"/messages"
        key = secrets.token_hex(16)
        status, sent = self.call(path, "POST", {"body": "Проверить размеры"}, owner, key=key)
        self.assertEqual(status, 201, sent)
        self.assertEqual(sent["message"]["sequence"], 1)
        self.assertEqual(self.call(path, "POST", {"body": "Проверить размеры"}, owner, key=key)[0], 200)
        self.assertEqual(self.call(path, "POST", {"body": "Другой текст"}, owner, key=key)[0], 409)
        self.plan(other)
        self.assertEqual(self.call(path, token=other)[0], 404)
        self.assertEqual(self.call(path+"?after=oops", token=owner)[0], 400)
        self.assertEqual(len(self.call(path, token=owner)[1]["items"]), 1)
        self.assertEqual(self.call(path+"?after=1", token=owner)[1]["items"], [])

    def test_payment_grants_workspace_and_refund_revokes_it(self):
        token, user_id = self.account("eco-paid")
        with self.mod.db() as con:
            user = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            intent = revenue.prepare_intent(con, user, "team-payment-fixture", "team_month", "pricing_page", False)
            remote = {"id": "eco-provider", "confirmation": {"confirmation_url": "https://pay.example.test/eco"}}
            local, _ = revenue.persist_checkout(con, user, "team-payment-fixture", "team_month", intent, remote)
            remote.update(status="succeeded", paid=True, test=False, recipient={"account_id": "eco-shop"},
                          amount={"value": "6990.00", "currency": "RUB"},
                          metadata={"user_id": user_id, "plan": "team_month"})
            handler = object.__new__(self.mod.Handler)
            env = {"YOOKASSA_MODE": "live", "YOOKASSA_SHOP_ID": "eco-shop",
                   "YOOKASSA_SECRET_KEY": "test", "YOOKASSA_MERCHANT_TYPE": "self_employed"}
            with patch.dict(os.environ, env):
                handler.apply_payment(con, local, remote)
                until = con.execute("SELECT entitlement_until FROM workspaces WHERE id=?", (intent["workspace_id"],)).fetchone()[0]
                handler.apply_payment(con, local, remote)
                self.assertEqual(until, con.execute("SELECT entitlement_until FROM workspaces WHERE id=?", (intent["workspace_id"],)).fetchone()[0])
                self.assertEqual(con.execute("SELECT plan,seat_limit FROM workspaces WHERE id=?", (intent["workspace_id"],)).fetchone()["seat_limit"], 5)
                handler.apply_refund(con, {"id": "eco-refund", "payment_id": "eco-provider", "status": "succeeded",
                                          "amount": {"value": "6990.00", "currency": "RUB"}})
            self.assertEqual(con.execute("SELECT plan FROM workspaces WHERE id=?", (intent["workspace_id"],)).fetchone()[0], "free")

    def test_cash_risk_uses_real_receipts_and_dedupes_retries(self):
        from types import SimpleNamespace
        from backend.business import Service
        from backend.cash_control import update_project_risk
        owner, user_id = self.account("eco-risk")
        wid = self.plan(owner, "pro_plus_month")
        moment = self.mod.now()
        with self.mod.db() as con:
            con.execute("INSERT INTO projects(id,workspace_id,name,amount_kopecks,created_at,updated_at) VALUES('eco-p',?,'Объект',100000,?,?)", (wid, moment, moment))
            con.execute("INSERT INTO expenses(id,workspace_id,project_id,amount_kopecks,category,expense_date,idempotency_key,created_at) VALUES('eco-e',?,'eco-p',5000,'Материалы','2026-10-24','risk-fixture-key',?)", (wid, moment))
            service = Service(SimpleNamespace(), con, "")
            service.wid, service.user = wid, {"id": user_id}
            with patch("backend.push.is_configured", return_value=True):
                result = update_project_risk(service, "eco-p")
                update_project_risk(service, "eco-p")
            self.assertEqual(result["deficit_kopecks"], 5000)
            self.assertEqual(con.execute("SELECT count(*) FROM push_outbox WHERE workspace_id=?", (wid,)).fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT recipient_user_id FROM push_outbox WHERE workspace_id=?", (wid,)).fetchone()[0], user_id)
            con.execute("INSERT INTO project_payments(id,workspace_id,project_id,amount_kopecks,payment_date,method,idempotency_key,created_at) VALUES('eco-r',?,'eco-p',8000,'2026-10-24','cash','risk-receipt-key',?)", (wid, moment))
            self.assertEqual(update_project_risk(service, "eco-p")["deficit_kopecks"], 0)

    def test_realtime_never_mints_a_token_without_explicit_signing_configuration(self):
        from types import SimpleNamespace
        service = SimpleNamespace(user={"id": "u"}, wid="w", h=SimpleNamespace(session_token_hash="a"*64))
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(object_chats.realtime_ticket(service, {"id": "t"}), {"configured": False})
        env = {"SUPABASE_REALTIME_JWT_SECRET": "test-only-secret-"*4,
               "SUPABASE_URL": "https://example.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "publishable"}
        with patch.dict(os.environ, env, clear=True):
            ticket = object_chats.realtime_ticket(service, {"id": "t"})
        import base64
        claims = json.loads(base64.urlsafe_b64decode(ticket["access_token"].split(".")[1]+"=="))
        self.assertEqual(claims["smetra_session"], "a"*64)
        self.assertEqual(claims["exp"]-claims["iat"], 120)
