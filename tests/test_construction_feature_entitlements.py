"""Server plan protection for premium construction planning and future modules."""
import unittest
from backend.entitlements import evaluate_workspace_plan


def plan(code, until=2_000_000_000, status="active"):
    return {"plan": code, "entitlement_until": until, "subscription_status": status}


class FeatureEntitlementTests(unittest.TestCase):
    def test_schedule_and_warehouse_are_pro_plus(self):
        for code in ("free", "pro", "pro_solo"):
            self.assertFalse(evaluate_workspace_plan(plan(code), "smart_timeline", 1_900_000_000)["allowed"])
            self.assertFalse(evaluate_workspace_plan(plan(code), "material_inventory", 1_900_000_000)["allowed"])
        for code in ("pro_plus", "team"):
            self.assertTrue(evaluate_workspace_plan(plan(code), "smart_timeline", 1_900_000_000)["allowed"])
            self.assertTrue(evaluate_workspace_plan(plan(code), "material_inventory", 1_900_000_000)["allowed"])

    def test_virtual_tour_is_team_only(self):
        self.assertFalse(evaluate_workspace_plan(plan("pro_plus"), "virtual_tours", 1_900_000_000)["allowed"])
        self.assertTrue(evaluate_workspace_plan(plan("team"), "virtual_tours", 1_900_000_000)["allowed"])

    def test_expired_or_unpaid_subscriptions_do_not_unlock(self):
        for feature in ("smart_timeline", "material_inventory", "virtual_tours"):
            for status in ("canceled", "refunded", "pending"):
                self.assertFalse(evaluate_workspace_plan(plan("team", status=status), feature, 1_900_000_000)["allowed"])
            self.assertFalse(evaluate_workspace_plan(plan("team", until=1_800_000_000), feature, 1_900_000_000)["allowed"])
        self.assertFalse(evaluate_workspace_plan(None, "smart_timeline", 1_900_000_000)["allowed"])


if __name__ == "__main__":
    unittest.main()
