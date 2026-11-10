"""Supplement decisions update the existing order atomically, exactly once."""
import unittest

from tests import test_protected_estimates as protected


class ProtectedChangeTests(unittest.TestCase):
    setUpClass = classmethod(protected.ProtectedEstimateTests.setUpClass.__func__)
    tearDownClass = classmethod(protected.ProtectedEstimateTests.tearDownClass.__func__)
    setUp = protected.ProtectedEstimateTests.setUp
    call = protected.ProtectedEstimateTests.call
    account = protected.ProtectedEstimateTests.account

    def supplement(self, items=None):
        with self.mod.db() as con:
            con.execute("UPDATE users SET entitlement_until=? WHERE id=?", (self.mod.now()+86400, self.owner_id))
        code, result = self.call("/projects", "POST", {"name": "Заказ", "amount_kopecks": 1000000, "internal_cost": 500000, "due_date": "2026-12-01"}, self.owner)
        self.assertEqual(code, 201, result)
        self.project = result["item"]
        code, result = self.call("/construction/objects", "POST", {"name": "Квартира", "project_id": self.project["id"]}, self.owner)
        self.assertEqual(code, 201, result)
        self.obj = result["object"]
        # Project attachment is normally created with the approved base quote;
        # this fixture supplies the same relationship without accepting another offer.
        with self.mod.db() as con:
            con.execute("UPDATE construction_objects SET project_id=? WHERE id=?", (self.project["id"], self.obj["id"]))
        self.path = "/construction/objects/"+self.obj["id"]+"/changes"
        code, result = self.call(self.path, "POST", {"title": "Дополнительные розетки", "deadline_days": 3,
            "items": items or [{"name": "Розетка", "quantity": "2", "unit_price": 50000, "cost_price": 20000}]}, self.owner)
        self.assertEqual(code, 201, result)
        self.change = result["change"]
        code, result = self.call(self.path+"/"+self.change["id"]+"/protect", "POST", {"review_confirmed": True}, self.owner)
        self.assertEqual(code, 200, result)
        self.extra = result["quote"]
        code, result = self.call("/protected-links", "POST", {"quote_id": self.extra["id"], "recipient_email": self.recipient_email}, self.owner)
        self.assertEqual(code, 201, result)
        self.token = result["url"].split("#")[1]
        code, opened = self.call("/public/protected/open", "POST", {"token": self.token})
        self.assertEqual(code, 200, opened)
        self.payload = {"token": self.token, "view_token": opened["view_token"], "confirmation": True,
            "snapshot_sha256": opened["document"]["snapshot_sha256"], "permissions_revision": opened["document"]["permissions_revision"], "action": "approved"}

    def test_verified_decision_and_retry_apply_budget_and_stage_once(self):
        self.supplement()
        self.assertEqual(self.call("/public/protected/respond", "POST", self.payload, self.owner)[0], 403)
        self.assertEqual(self.call("/public/protected/respond", "POST", self.payload, self.recipient)[0], 200)
        self.assertEqual(self.call("/public/protected/respond", "POST", self.payload, self.recipient)[0], 200)
        result = self.call("/projects/"+self.project["id"], token=self.owner)[1]["item"]
        self.assertEqual(result["amount_kopecks"], 1100000)
        self.assertEqual(result["internal_cost"], self.project["internal_cost"]+40000)
        self.assertEqual(result["due_date"], "2026-12-04")
        self.assertEqual(len(result["stages"]), 1)
        self.assertEqual(result["stages"][0]["amount_kopecks"], 100000)
        self.assertEqual(self.call("/quotes/"+self.extra["id"]+"/project", "POST", {}, self.owner)[0], 409)

    def test_immutable_supplement_and_revocation(self):
        self.supplement()
        self.assertEqual(self.call("/quotes/"+self.extra["id"], "PATCH", {"revision": self.extra["revision"], "terms": "Другие условия"}, self.owner)[0], 409)
        self.assertEqual(self.call(self.path+"/"+self.change["id"]+"/revoke", "POST", {}, self.owner)[0], 200)
        self.assertEqual(self.call("/public/protected/respond", "POST", self.payload, self.recipient)[0], 410)
        result = self.call("/projects/"+self.project["id"], token=self.owner)[1]["item"]
        self.assertEqual(result["amount_kopecks"], self.project["amount_kopecks"])

    def test_fractional_effective_price_does_not_change_agreed_total(self):
        self.supplement(items=[{"name": "Мелкие работы", "quantity": "3", "unit_price": 100, "discount": "33.33", "cost_price": 20}])
        self.assertEqual(self.change["amount_kopecks"], 200)
        self.assertEqual(self.extra["amount_kopecks"], 200)
        self.assertEqual(self.extra["internal_cost"], 60)
        self.assertEqual(self.call("/public/protected/respond", "POST", self.payload, self.recipient)[0], 200)
        result = self.call("/projects/"+self.project["id"], token=self.owner)[1]["item"]
        self.assertEqual(result["amount_kopecks"], self.project["amount_kopecks"]+200)


if __name__ == "__main__":
    unittest.main()
