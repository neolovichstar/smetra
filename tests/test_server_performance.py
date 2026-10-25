"""Database round-trip budgets preserve quota semantics and workspace isolation."""

import sqlite3
import unittest
from pathlib import Path

from backend import assistant, business


class RecordingConnection:
    def __init__(self, con):
        self.con = con
        self.queries = []

    def execute(self, sql, parameters=()):
        self.queries.append(sql)
        return self.con.execute(sql, parameters)


class ServerPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(":memory:", isolation_level=None)
        self.raw.row_factory = sqlite3.Row
        self.raw.executescript((Path(__file__).parents[1] / "backend/schema.sql").read_text())
        business.migrate(self.raw)
        self.raw.execute(
            "INSERT INTO users(id,email,password_hash,name,created_at,plan,entitlement_until) VALUES(?,?,?,?,?,?,?)",
            ("perf-user", "perf@test.invalid", "unused", "Perf", business.stamp(), "pro", business.stamp() + 86400),
        )
        self.user = self.raw.execute("SELECT * FROM users WHERE id='perf-user'").fetchone()
        self.wid = business.ensure_workspace(self.raw, self.user)
        self.con = RecordingConnection(self.raw)
        self.service = business.Service(None, self.con, "http://localhost")
        self.service.user, self.service.wid, self.service.role = self.user, self.wid, "owner"

    def tearDown(self):
        self.raw.close()

    def test_quota_is_one_fresh_query_and_observes_updated_counters(self):
        first = assistant.quota(self.service)
        self.assertEqual(len(self.con.queries), 1)
        self.assertEqual((first["limit"], first["used"], first["remaining"]), (100, 0, 100))
        self.raw.execute("INSERT INTO rate_limits(key,count,started) VALUES(?,7,?)", (first["key"], business.stamp()))
        self.con.queries.clear()
        second = assistant.quota(self.service)
        self.assertEqual(len(self.con.queries), 1)
        self.assertEqual((second["used"], second["remaining"]), (7, 93))
        self.assertNotIn("key", assistant.public_quota(self.service))

    def test_dashboard_stops_fetching_cards_after_priority_groups_fill_the_response(self):
        for index in range(5):
            self.raw.execute(
                "INSERT INTO leads(id,workspace_id,name,created_at,updated_at) VALUES(?,?,?,?,?)",
                ("lead-" + str(index), self.wid, "Lead", index, index),
            )
            self.raw.execute(
                "INSERT INTO quotes(id,user_id,workspace_id,public_token,title,client,amount_kopecks,"
                "created_at,updated_at,approval_state,approved_at,description) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ("quote-" + str(index), self.user["id"], self.wid, "public-" + str(index),
                 "Quote", "Client", 100, index, index, "approved", business.stamp(), ""),
            )
        result = self.service.action_center()
        self.assertEqual(len(result["items"]), 8)
        self.assertEqual([row["kind"] for row in result["items"]], ["lead"] * 5 + ["quote"] * 3)
        self.assertEqual(result["summary"]["approved_this_month"], 5)
        self.assertEqual(len(self.con.queries), 4)

    def test_empty_dashboard_keeps_zero_counts_and_bounded_queries(self):
        result = self.service.action_center()
        self.assertEqual(result["items"], [])
        self.assertEqual(result["summary"], {
            "active_projects": 0, "waiting_payments": 0, "approved_this_month": 0,
            "received_this_month": {},
        })
        self.assertEqual(len(self.con.queries), 10)

    def test_history_lookup_uses_ordered_scoped_index(self):
        self.raw.execute(
            "INSERT INTO assistant_conversations(id,workspace_id,user_id,title,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("thread", self.wid, self.user["id"], "History", 1, 1),
        )
        for index in range(2000):
            self.raw.execute(
                "INSERT INTO assistant_messages(id,workspace_id,user_id,conversation_id,role,content,created_at) VALUES(?,?,?,?,?,?,?)",
                (f"msg-{index:05}", self.wid, self.user["id"], "thread" if index % 2 else None,
                 "user", "Text", index),
            )
        for thread in ("thread", None):
            condition = "conversation_id=?" if thread else "conversation_id IS NULL"
            args = (self.wid, self.user["id"], thread) if thread else (self.wid, self.user["id"])
            sql = ("SELECT id FROM assistant_messages WHERE workspace_id=? AND user_id=? AND " + condition +
                   " ORDER BY created_at DESC,id DESC LIMIT 30")
            plan = " ".join(row[3] for row in self.raw.execute("EXPLAIN QUERY PLAN " + sql, args))
            self.assertIn("idx_assistant_history_scope", plan)
            self.assertNotIn("TEMP B-TREE", plan)
            rows = self.raw.execute(sql, args).fetchall()
            self.assertEqual(len(rows), 30)
            self.assertEqual(rows[0][0], "msg-01999" if thread else "msg-01998")
