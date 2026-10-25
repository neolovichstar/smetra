import unittest

from backend import order_finance


class OrderFinanceMath(unittest.TestCase):
    def test_partial_payment_overrun_and_forecast(self):
        f = order_finance.summarize(100_000, 60_000, 30_000, 70_000)
        self.assertEqual(f["receivable"], 70_000)
        self.assertEqual(f["planned_profit"], 40_000)
        self.assertEqual(f["forecast_profit"], 30_000)
        self.assertEqual(f["cash_result"], -40_000)
        self.assertEqual(f["overrun"], 10_000)
        self.assertEqual(f["budget_used_pct"], 117)
        self.assertEqual(f["paid_pct"], 30)

    def test_overpaid_and_no_plan(self):
        f = order_finance.summarize(50_000, 0, 60_000, 5_000)
        self.assertEqual((f["receivable"], f["overpaid"]), (0, 10_000))
        self.assertIsNone(f["budget_used_pct"])
        self.assertEqual(f["overrun"], 0, "Without a planned cost there is nothing to overrun")
        self.assertEqual(f["forecast_profit"], 45_000)
        self.assertIsNone(f["planned_profit"])

    def test_profit_is_unknown_without_any_cost(self):
        f = order_finance.summarize(310_000, 0, 180_000, 0)
        self.assertIsNone(f["forecast_profit"], "A missing cost must not read as a 100% margin")
        self.assertIsNone(f["planned_profit"])
        self.assertEqual(f["cash_result"], 180_000)

    def test_percent_rounds_half_up_and_handles_zero(self):
        self.assertEqual(order_finance.percent(1, 8), 13)
        self.assertEqual(order_finance.percent(1, 3), 33)
        self.assertIsNone(order_finance.percent(5, 0))
        self.assertEqual(order_finance.summarize(0, 0, 0, 0)["paid_pct"], None)
