"""Partner console sign-in with the Smetra account, roles and the partner team."""
import http.client
import json
import re
import time
import unittest

from backend import partner_access as access, partner_platform as partner
from backend.partner_platform import PartnerError
from tests import test_business


class PartnerAccessTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def raw(self, method, path, host="smetra.online", token=None, body=None, header=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        headers = {"Host": host}
        if token:
            headers["Authorization"] = "Bearer " + token
        if header:
            headers["Authorization"] = header
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = conn.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, dict(response.getheaders()), (json.loads(text) if text.startswith("{") else text)
        finally:
            conn.close()

    def partner(self, code, host):
        with self.mod.db() as con:
            created = partner.create_partner(con, {"code": code, "name": code.title(), "allowed_host": host})
        return created["id"]

    def verified(self, user_id):
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=? WHERE id=?", (int(time.time()), user_id))

    def sso_code(self, token):
        status, headers, _ = self.raw("GET", "/api/partners/v1/sso/start", token=token)
        self.assertEqual(status, 302)
        match = re.fullmatch(r"https://console\.smetra\.online/app#sso=([A-Za-z0-9_-]{40,60})", headers["Location"])
        self.assertIsNotNone(match, headers["Location"])
        return match[1]

    def console(self, method, path, session=None, body=None):
        return self.raw(method, "/api/partners/v1/console" + path, host="console.smetra.online",
                        header=("PartnerSession " + session) if session else None, body=body)

    def test_account_sign_in_needs_an_invited_verified_email(self):
        token, user_id = self.account("partner-owner")
        status, headers, _ = self.raw("GET", "/api/partners/v1/sso/start")
        self.assertEqual(status, 302)
        self.assertTrue(headers["Location"].endswith("/app?partner_sso=1"))
        # The console host never serves the account-side start route.
        self.assertEqual(self.raw("GET", "/api/partners/v1/sso/start", host="console.smetra.online", token=token)[0], 404)

        partner_id = self.partner("store-one", "store-one.ru")
        with self.mod.db() as con:
            access.admin_invite_owner(con, partner_id, "partner-owner@test.invalid")
        # Unconfirmed email: the invitation is not accepted, no access.
        with self.mod.db() as con:
            con.execute("UPDATE users SET email_verified_at=NULL WHERE id=?", (user_id,))
        status, _, body = self.console("POST", "/session/sso", body={"code": self.sso_code(token)})
        self.assertEqual(status, 403, body)
        self.verified(user_id)
        code = self.sso_code(token)
        status, _, body = self.console("POST", "/session/sso", body={"code": code})
        self.assertEqual(status, 201, body)
        self.assertEqual(body["partner"]["role"], "owner")
        session = body["session_token"]
        # One-time code.
        self.assertEqual(self.console("POST", "/session/sso", body={"code": code})[0], 401)
        status, _, me = self.console("GET", "/me", session)
        self.assertEqual((status, me["role"], me["user"]["email"]), (200, "owner", "partner-owner@test.invalid"))
        self.assertIn("team", me["permissions"])
        self.assertEqual(self.console("GET", "/summary", session)[0], 200)

    def test_roles_are_checked_on_the_server_and_removal_is_immediate(self):
        owner_token, owner_id = self.account("role-owner")
        analyst_token, analyst_id = self.account("role-analyst")
        catalog_token, catalog_id = self.account("role-catalog")
        for user_id in (owner_id, analyst_id, catalog_id):
            self.verified(user_id)
        partner_id = self.partner("store-roles", "store-roles.ru")
        with self.mod.db() as con:
            access.admin_invite_owner(con, partner_id, "role-owner@test.invalid")
        owner = self.console("POST", "/session/sso", body={"code": self.sso_code(owner_token)})[2]["session_token"]
        for email, role in (("role-analyst@test.invalid", "analyst"), ("role-catalog@test.invalid", "catalog")):
            status, _, body = self.console("POST", "/team/invites", owner, {"email": email, "role": role})
            self.assertEqual(status, 201, body)
        analyst = self.console("POST", "/session/sso", body={"code": self.sso_code(analyst_token)})[2]["session_token"]
        catalog = self.console("POST", "/session/sso", body={"code": self.sso_code(catalog_token)})[2]["session_token"]

        self.assertEqual(self.console("GET", "/analytics?days=30", analyst)[0], 200)
        self.assertEqual(self.console("GET", "/commissions", analyst)[0], 200)
        self.assertEqual(self.console("POST", "/catalog", analyst, {"products": []})[0], 403)
        self.assertEqual(self.console("GET", "/team", analyst)[0], 403)
        self.assertEqual(self.console("GET", "/commissions", catalog)[0], 403)
        self.assertEqual(self.console("GET", "/summary", catalog)[0], 403)
        self.assertEqual(self.console("GET", "/products", catalog)[0], 200)

        status, _, team = self.console("GET", "/team", owner)
        self.assertEqual(status, 200)
        self.assertEqual({m["role"] for m in team["members"]}, {"owner", "analyst", "catalog"})
        self.assertEqual(self.console("POST", f"/team/members/{analyst_id}/remove", owner, {})[0], 200)
        self.assertEqual(self.console("GET", "/me", analyst)[0], 401, "removed member keeps no session")
        # The last owner cannot leave or be demoted.
        self.assertEqual(self.console("POST", f"/team/members/{owner_id}/role", owner, {"role": "admin"})[0], 409)
        self.assertEqual(self.console("POST", f"/team/members/{owner_id}/remove", owner, {})[0], 409)

    def test_admin_cannot_touch_owners_and_partners_stay_isolated(self):
        with self.mod.db() as con:
            first = partner.create_partner(con, {"code": "iso-one", "name": "One", "allowed_host": "iso-one.ru"})
            second = partner.create_partner(con, {"code": "iso-two", "name": "Two", "allowed_host": "iso-two.ru"})
            con.execute("INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES('u-own','own@x.ru','x','Own',1,1)")
            con.execute("INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES('u-adm','adm@x.ru','x','Adm',1,1)")
            con.execute("INSERT INTO partner_members(partner_id,user_id,role,created_at) VALUES(?,?,?,1)", (first["id"], "u-own", "owner"))
            con.execute("INSERT INTO partner_members(partner_id,user_id,role,created_at) VALUES(?,?,?,1)", (first["id"], "u-adm", "admin"))
            account = con.execute("SELECT * FROM partner_accounts WHERE id=?", (first["id"],)).fetchone()
            with self.assertRaises(PartnerError):
                access.invite(con, account, "admin", "u-adm", {"email": "new@x.ru", "role": "owner"})
            with self.assertRaises(PartnerError):
                access.change_role(con, account, "admin", "u-adm", "u-own", {"role": "analyst"})
            with self.assertRaises(PartnerError):
                access.remove_member(con, account, "admin", "u-adm", "u-own")
            other = con.execute("SELECT * FROM partner_accounts WHERE id=?", (second["id"],)).fetchone()
            with self.assertRaises(PartnerError):
                access.change_role(con, other, "owner", "u-own", "u-adm", {"role": "analyst"})
            self.assertEqual(access.team(con, other)["members"], [])
            with self.assertRaises(PartnerError):
                access.require("analyst", "catalog_write")
            access.require("key", "catalog_write")
            with self.assertRaises(PartnerError):
                access.require("key", "team")


if __name__ == "__main__":
    unittest.main()
