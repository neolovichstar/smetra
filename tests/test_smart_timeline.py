"""Tests for the deterministic timeline preview; no user data or external AI."""
import unittest

from backend.smart_timeline import TimelineError, preview


class SmartTimelineTests(unittest.TestCase):
    def test_workdays_and_manual_curing(self):
        report = preview({
            "start_date": "2026-10-26",
            "stages": [
                {"id": "plaster", "name": "Штукатурка",
                 "quantity": "100", "daily_output": "20", "curing_days": 7},
                {"id": "tile", "name": "Плитка", "depends_on": ["plaster"],
                 "duration_days": 2},
            ],
        })
        self.assertEqual(report["stages"][0]["end_date"], "2026-10-30")
        self.assertEqual(report["stages"][1]["start_date"], "2026-11-09")
        self.assertEqual(report["end_date"], "2026-11-10")
        self.assertEqual(report["stages"][0]["duration_days"], 5)
        self.assertIn("специалист", report["disclaimer"])

    def test_parallel_dependencies(self):
        report = preview({"start_date": "2026-10-26", "stages": [
            {"id": "b", "name": "Задача Б", "duration_days": 1},
            {"id": "c", "name": "Задача В", "depends_on": ["a", "b"], "duration_days": 2},
            {"id": "a", "name": "Задача А", "duration_days": 3},
        ]})
        self.assertEqual(report["stages"][0]["start_date"], "2026-10-26")
        self.assertEqual(report["stages"][1]["start_date"], "2026-10-29")
        self.assertEqual(report["stages"][1]["end_date"], "2026-10-30")

    def test_calendar_mode_and_delays(self):
        report = preview({"start_date": "2026-10-24", "workdays_only": False, "stages": [
            {"id": "one", "name": "Разбор", "duration_days": 2, "delay_days": 3},
            {"id": "two", "name": "Монтаж", "duration_days": 1, "depends_on": ["one"]},
        ]})
        self.assertEqual(report["stages"][0]["end_date"], "2026-10-28")
        self.assertEqual(report["stages"][1]["start_date"], "2026-10-29")
        self.assertEqual(report["end_date"], "2026-10-29")

    def test_quantities_round_up(self):
        r = preview({"start_date": "2026-10-26", "stages": [
            {"id": "x", "name": "Грунтование", "quantity": "10.01", "daily_output": "10"},
        ]})
        self.assertEqual(r["stages"][0]["duration_days"], 2)

    def test_reject_invalid_durations_and_dependencies(self):
        base = {"start_date": "2026-10-26"}
        bad = [
            [{"id": "x", "name": "А", "duration_days": 0}],
            [{"id": "x", "name": "А", "quantity": "2", "daily_output": "0"}],
            [{"id": "x", "name": "А", "duration_days": 1, "curing_days": -1}],
            [{"id": "x", "name": "А", "duration_days": 1, "delay_days": "NaN"}],
            [{"id": "x", "name": "А", "duration_days": 1, "depends_on": ["missing"]}],
            [{"id": "x", "name": "А", "duration_days": 1, "depends_on": ["x"]}],
            [{"id": "x", "name": "А", "duration_days": 1},
             {"id": "x", "name": "Б", "duration_days": 1}],
            [{"id": "x", "name": "А", "duration_days": 1, "depends_on": ["y"]},
             {"id": "y", "name": "Б", "duration_days": 1, "depends_on": ["x"]}],
            [{"id": "x", "name": "А", "duration_days": True}],
            [{"id": "x", "name": "А", "quantity": "1e9999", "daily_output": "1"}],
        ]
        for stages in bad:
            with self.subTest(stages=stages), self.assertRaises(TimelineError):
                preview({**base, "stages": stages})
        with self.assertRaises(TimelineError):
            preview({**base, "stages": []})
        with self.assertRaises(TimelineError):
            preview({"start_date": "2026-02-30", "stages": [
                {"id": "x", "name": "А", "duration_days": 1}
            ]})

    def test_no_input_mutation(self):
        payload = {"start_date": "2026-10-26", "stages": [
            {"id": "a", "name": "Шпаклёвка", "quantity": 100, "daily_output": 25}
        ]}
        preview(payload)
        self.assertEqual(payload["stages"][0], {
            "id": "a", "name": "Шпаклёвка", "quantity": 100, "daily_output": 25
        })


if __name__ == "__main__":
    unittest.main()
