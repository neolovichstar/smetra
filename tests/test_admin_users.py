"""Administrator page for one account: plan, tokens, access, all audited."""
import unittest

from backend import ai_tokens
from tests.test_business import BusinessFlows


class AdminUserPageTests(unittest.TestCase):
    setUpClass = classmethod(BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(BusinessFlows.tearDownClass.__func__)
    setUp = BusinessFlows.setUp
    call = BusinessFlows.call
    account = BusinessFlows.account

    def admin(self, name):
        token, user_id = self.account(name)
        with self.mod.db() as con:
            con.execute("UPDATE users SET role='admin' WHERE id=?", (user_id,))
        return token, user_id

    def act(self, admin, target, body):
        return self.call("/admin/users/" + target, "PATCH", body, admin)

    def test_detail_requires_admin_and_lists_account_state(self):
        admin, _ = self.admin("page-admin")
        member, member_id = self.account("page-member")
        self.assertEqual(self.call("/admin/users/" + member_id, token=member)[0], 403)
        status, page = self.call("/admin/users/" + member_id, token=admin)
        self.assertEqual(status, 200, page)
        self.assertEqual(page["user"]["email"], "page-member@test.invalid")
        self.assertEqual(page["tokens"]["unit"], "tokens")
        self.assertNotIn("key", page["tokens"])
        self.assertTrue(any(w["personal"] for w in page["workspaces"]))
        self.assertIn("pro_plus", page["plans"])
        self.assertEqual(self.call("/admin/users/nobody", token=admin)[0], 404)

    def test_plan_tokens_access_and_role_changes_are_audited(self):
        admin, admin_id = self.admin("page-owner")
        member, member_id = self.account("page-target")
        self.assertEqual(self.act(admin, member_id, {"action": "set_plan", "plan": "pro_plus", "days": 30, "reason": "Партнёр"})[0], 200)
        page = self.call("/admin/users/" + member_id, token=admin)[1]
        personal = next(w for w in page["workspaces"] if w["personal"])
        self.assertEqual(personal["tier"], "pro_plus")
        self.assertEqual(page["tokens"]["monthly_limit"], ai_tokens.MONTHLY_TOKENS["pro_plus"])
        self.assertEqual(self.act(admin, member_id, {"action": "set_plan", "plan": "pro_plus", "days": 0})[0], 400)
        self.assertEqual(self.act(admin, member_id, {"action": "set_plan", "plan": "gold", "days": 5})[0], 400)

        status, result = self.act(admin, member_id, {"action": "tokens", "delta": 250000, "reason": "Компенсация"})
        self.assertEqual((status, result["wallet"]), (200, 250000))
        status, result = self.act(admin, member_id, {"action": "tokens", "delta": -400000})
        self.assertEqual((status, result["wallet"]), (200, 0), "wallet never goes below zero")
        self.assertEqual(self.act(admin, member_id, {"action": "tokens", "delta": "много"})[0], 400)
        self.assertEqual(self.call("/assistant", token=member)[1]["quota"]["wallet"], 0)

        self.assertEqual(self.act(admin, member_id, {"action": "block", "reason": "Спам"})[0], 200)
        self.assertEqual(self.call("/me", token=member)[0], 401, "blocking ends every session")
        self.assertEqual(self.act(admin, member_id, {"action": "unblock"})[0], 200)
        self.assertEqual(self.act(admin, admin_id, {"action": "block"})[0], 409)
        self.assertEqual(self.act(admin, admin_id, {"action": "role", "role": "user"})[0], 409)
        self.assertEqual(self.act(admin, member_id, {"action": "role", "role": "admin"})[0], 200)
        self.assertEqual(self.act(admin, member_id, {"action": "sessions_revoke"})[0], 200)
        self.assertEqual(self.act(admin, member_id, {"action": "set_plan", "plan": "free"})[0], 200)

        page = self.call("/admin/users/" + member_id, token=admin)[1]
        actions = {row["action"] for row in page["audit"]}
        self.assertTrue({"admin.set_plan.pro_plus", "admin.tokens", "admin.block", "admin.unblock",
                         "admin.role.admin", "admin.sessions_revoke", "admin.set_plan.free"} <= actions)
        reasons = [row["reason"] for row in page["ledger"]]
        self.assertEqual(reasons.count("admin_adjust"), 2)
        self.assertEqual(next(w for w in page["workspaces"] if w["personal"])["tier"], "starter")


if __name__ == "__main__":
    unittest.main()
