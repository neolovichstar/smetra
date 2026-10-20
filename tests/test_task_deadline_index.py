"""Regression tests for indexes supporting the dashboard's active deadline list."""
from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
SQLITE_MIGRATION = ROOT / "backend" / "migrations" / "026_tasks_open_due_index.sql"
POSTGRES_MIGRATION = (
    ROOT / "supabase" / "migrations" / "20261020121500_tasks_open_due_index.sql"
)
QUERY = (
    "SELECT id, name, due_date, status FROM tasks "
    "WHERE workspace_id=? AND due_date!='' AND status!='done' "
    "ORDER BY due_date LIMIT ?"
)


class TaskDeadlineIndexTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at INTEGER NOT NULL
            );
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                name TEXT NOT NULL,
                due_date TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo'
            );
            """
        )

    def tearDown(self):
        self.con.close()

    def test_partial_index_is_used_for_active_deadlines(self):
        self.con.executescript(SQLITE_MIGRATION.read_text(encoding="utf-8"))
        self.con.executemany(
            "INSERT INTO tasks(id,workspace_id,name,due_date,status) VALUES(?,?,?,?,?)",
            [
                ("active", "w1", "Active task", "2026-10-20", "todo"),
                ("done", "w1", "Finished task", "2026-10-19", "done"),
                ("undated", "w1", "No deadline", "", "todo"),
                ("other", "w2", "Other workspace", "2026-10-21", "todo"),
            ],
        )
        plan = " ".join(str(row[3]) for row in self.con.execute("EXPLAIN QUERY PLAN " + QUERY, ("w1", 10)))
        self.assertIn("idx_tasks_workspace_open_due", plan)
        rows = self.con.execute(QUERY, ("w1", 10)).fetchall()
        self.assertEqual([row[0] for row in rows], ["active"])
        applied = self.con.execute(
            "SELECT applied_at FROM schema_migrations WHERE version=36"
        ).fetchone()
        self.assertIsNotNone(applied)

    def test_postgres_migration_matches_index_and_has_timeouts(self):
        sql = POSTGRES_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_tasks_workspace_open_due", sql)
        self.assertIn("ON smetra.tasks(workspace_id, due_date)", sql)
        self.assertIn("WHERE due_date <> '' AND status <> 'done'", sql)
        self.assertIn("SET LOCAL lock_timeout='5s'", sql)
        self.assertIn("SET LOCAL statement_timeout='30s'", sql)
        self.assertIn("VALUES (39, extract(epoch FROM now())::BIGINT)", sql)


if __name__ == "__main__":
    unittest.main()
