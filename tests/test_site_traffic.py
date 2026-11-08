"""No personal data in anonymous audience counters; one browser per day."""
import sqlite3
import unittest
import uuid

from backend import traffic


class SiteTrafficTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        traffic.ensure_schema(self.con)

    def tearDown(self):
        self.con.close()

    def test_day_dedupe_multiple_pages_and_views(self):
        client1 = str(uuid.uuid4())
        client2 = str(uuid.uuid4())
        ts = 1_783_680_000
        traffic.record(self.con, client1, "landing", timestamp=ts)
        traffic.record(self.con, client1, "landing", timestamp=ts)
        traffic.record(self.con, client1, "app", timestamp=ts)
        traffic.record(self.con, client2, "landing", timestamp=ts)
        summary = traffic.overview(self.con, timestamp=ts)
        self.assertEqual((summary["today"], summary["week"], summary["month"]), (2, 2, 2))
        self.assertEqual(summary["views_30d"], 4)
        self.assertEqual(len(summary["daily"]), 30)
        self.assertEqual(summary["daily"][-1]["views"], 4)
        self.assertEqual(sum(page["visitors"] for page in summary["pages"]), 3)
        rows = self.con.execute("SELECT * FROM site_visits").fetchall()
        self.assertEqual(len(rows), 3)
        self.assertNotIn(client1, str([dict(row) for row in rows]))
        self.assertTrue(all(len(row["visitor_hash"]) == 64 for row in rows))

    def test_unique_over_seven_and_thirty_days(self):
        client = str(uuid.uuid4())
        second = str(uuid.uuid4())
        ts = 1_783_680_000
        traffic.record(self.con, client, "landing", timestamp=ts-20*86400)
        traffic.record(self.con, client, "landing", timestamp=ts-2*86400)
        traffic.record(self.con, second, "app", timestamp=ts-3*86400)
        summary = traffic.overview(self.con, timestamp=ts)
        self.assertEqual(summary["today"], 0)
        self.assertEqual(summary["week"], 2)
        self.assertEqual(summary["month"], 2)
        self.assertEqual(summary["views_30d"], 3)

    def test_invalid_ids_and_pages_fail_closed(self):
        client = str(uuid.uuid4())
        for visitor, page in [
            ("", "app"), ("1 OR 1=1", "app"),
            (str(uuid.uuid1()), "app"),
            (client, "admin"), (client, "unknown"),
            (None, "app"), ({}, "landing"),
        ]:
            with self.assertRaises((ValueError, TypeError, AttributeError)):
                traffic.record(self.con, visitor, page)
        self.assertEqual(self.con.execute("SELECT count(*) FROM site_visits").fetchone()[0], 0)

    def test_reload_views_are_bounded(self):
        client = str(uuid.uuid4())
        for _ in range(105):
            traffic.record(self.con, client, "landing", timestamp=1_783_680_000)
        row = self.con.execute("SELECT count(*) AS n, max(views) AS v FROM site_visits").fetchone()
        self.assertEqual((row["n"], row["v"]), (1, 100))


if __name__ == "__main__":
    unittest.main()
