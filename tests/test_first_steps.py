"""First-steps checklist: /api/me reports the path-to-value milestones the person reached."""
import unittest

from tests import test_business


class FirstSteps(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account
    publish = test_business.BusinessFlows.publish

    def test_milestones_follow_create_and_share(self):
        token, _ = self.account("first-steps")
        me = self.call("/me", token=token)[1]["user"]
        self.assertEqual((me["quote_count"], me["milestones"]), (0, []))
        status, created = self.call("/quotes", "POST", {"title": "Ванная", "client": "Анна", "amount": 10000}, token)
        self.assertEqual(status, 201, created)
        self.assertEqual(self.call("/me", token=token)[1]["user"]["milestones"], ["estimate_created"])
        self.publish(token, created["quote"])
        self.assertEqual(self.call("/me", token=token)[1]["user"]["milestones"], ["estimate_created", "estimate_shared"])


if __name__ == "__main__":
    unittest.main()
