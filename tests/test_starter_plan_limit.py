"""Public starter terms and server enforcement must describe the same lifetime limit."""
import datetime as dt
import unittest
from pathlib import Path

from backend import plan_catalog


ROOT = Path(__file__).resolve().parents[1]


class StarterPlanLimits(unittest.TestCase):
    def test_new_and_legacy_allowances_are_consistent(self):
        self.assertEqual(plan_catalog.CATALOG["starter"]["free_quotes"], 3)
        self.assertEqual(plan_catalog.public_catalog()["starter"]["free_quotes"], 3)
        self.assertEqual(plan_catalog.starter_quote_limit({"created_at": plan_catalog.STARTER_LEGACY_CUTOFF - 1}), 10)
        self.assertEqual(plan_catalog.starter_quote_limit({"created_at": plan_catalog.STARTER_LEGACY_CUTOFF}), 3)
        self.assertEqual(plan_catalog.starter_quote_limit({"created_at": plan_catalog.STARTER_LEGACY_CUTOFF + 1}), 3)
        cutoff = dt.datetime.fromtimestamp(plan_catalog.STARTER_LEGACY_CUTOFF, dt.timezone.utc)
        self.assertEqual(cutoff.isoformat(), "2026-10-28T12:28:00+00:00")

    def test_public_website_describes_three_new_quotes_not_monthly(self):
        for name in ("apps/web/index.html", "apps/web/ui/plans.js", "apps/web/terms.html"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("3 ", text, name)
            self.assertNotIn("10 бесплатных", text, name)
            self.assertNotIn("10 смет бесплатно", text, name)
        legal = (ROOT / "apps/web/terms.html").read_text(encoding="utf-8")
        self.assertIn("10 смет", legal, "Terms must preserve prior customers' entitlement")
        self.assertIn("Редактирование созданных смет не уменьшает лимит", legal)


if __name__ == "__main__":
    unittest.main()
