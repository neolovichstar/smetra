"""Regression tests for query-hot-path indexes and production RLS optimization."""
from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
SQLITE_MIGRATION = ROOT / "backend" / "migrations" / "025_query_hot_path_indexes.sql"
POSTGRES_MIGRATION = ROOT / "supabase" / "migrations" / "20261020110000_query_hot_path_rls_performance.sql"

EXPECTED_INDEXES = {
    "idx_events_user_name": ("events", ("user_id", "name")),
    "idx_quotes_workspace_approval_updated": ("quotes", ("workspace_id", "approval_state", "updated_at", "id")),
    "idx_quotes_workspace_approved_at": ("quotes", ("workspace_id", "approved_at")),
    "idx_quotes_workspace_sent_at": ("quotes", ("workspace_id", "sent_at")),
    "idx_quotes_workspace_first_viewed": ("quotes", ("workspace_id", "first_viewed_at")),
    "idx_projects_workspace_due_status": ("projects", ("workspace_id", "due_date", "status")),
    "idx_project_payments_workspace_project_created": ("project_payments", ("workspace_id", "project_id", "created_at")),
}


class QueryHotPathMigrationTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.executescript(
            """
            CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL);
            CREATE TABLE events(id TEXT PRIMARY KEY, user_id TEXT, name TEXT, created_at INTEGER);
            CREATE TABLE quotes(
                id TEXT PRIMARY KEY, workspace_id TEXT, approval_state TEXT, updated_at INTEGER,
                approved_at INTEGER, sent_at INTEGER, first_viewed_at INTEGER
            );
            CREATE TABLE projects(id TEXT PRIMARY KEY, workspace_id TEXT, due_date TEXT, status TEXT);
            CREATE TABLE project_payments(
                id TEXT PRIMARY KEY, workspace_id TEXT, project_id TEXT, created_at INTEGER
            );
            """
        )

    def tearDown(self):
        self.con.close()

    def apply_migration(self):
        self.con.executescript(SQLITE_MIGRATION.read_text(encoding="utf-8"))

    def test_sqlite_migration_creates_expected_composite_indexes(self):
        self.apply_migration()
        for index_name, (table, expected_columns) in EXPECTED_INDEXES.items():
            with self.subTest(index=index_name):
                row = self.con.execute(
                    "SELECT tbl_name FROM sqlite_master WHERE type='index' AND name=?",
                    (index_name,),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], table)
                actual = tuple(
                    value[2]
                    for value in self.con.execute(f"PRAGMA index_info('{index_name}')")
                )
                self.assertEqual(actual, expected_columns)

        version = self.con.execute(
            "SELECT applied_at FROM schema_migrations WHERE version=35"
        ).fetchone()
        self.assertIsNotNone(version)

    def test_dashboard_and_quota_queries_can_use_composite_indexes(self):
        self.apply_migration()
        self.con.executemany(
            "INSERT INTO events(id,user_id,name,created_at) VALUES(?,?,?,?)",
            [(f"e{i}", f"u{i % 9}", "quote_created" if i % 2 else "other", i) for i in range(900)],
        )
        self.con.executemany(
            """INSERT INTO quotes(id,workspace_id,approval_state,updated_at,approved_at,sent_at,first_viewed_at)
               VALUES(?,?,?,?,?,?,?)""",
            [(f"q{i}", f"w{i % 7}", "changes_requested" if i % 2 else "draft",
              i, i if i % 3 else None, i if i % 4 else None, i if i % 5 else None)
             for i in range(700)],
        )
        self.con.execute("ANALYZE")
        event_plan = " ".join(
            str(row[3])
            for row in self.con.execute(
                "EXPLAIN QUERY PLAN SELECT count(*) FROM events WHERE user_id=? AND name=?",
                ("u1", "quote_created"),
            )
        )
        quote_plan = " ".join(
            str(row[3])
            for row in self.con.execute(
                """EXPLAIN QUERY PLAN SELECT id FROM quotes
                   WHERE workspace_id=? AND approval_state=?
                   ORDER BY updated_at DESC, id LIMIT 5""",
                ("w1", "changes_requested"),
            )
        )
        self.assertIn("idx_events_user_name", event_plan)
        self.assertIn("idx_quotes_workspace_approval_updated", quote_plan)

    def test_postgres_migration_rewrites_rls_without_broadening_access(self):
        sql = POSTGRES_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("SET LOCAL lock_timeout='5s'", sql)
        self.assertIn("SET LOCAL statement_timeout='30s'", sql)
        self.assertIn("ALTER POLICY", sql)
        self.assertIn("policyname LIKE 'smetra_runtime%'", sql)
        self.assertIn("( SELECT current_setting(", sql)
        self.assertIn("( SELECT smetra.runtime_user_id())", sql)
        self.assertIn("runtime_workspace_allowed(NULLIF(current_setting(", sql)
        self.assertIn("VALUES (38, extract(epoch FROM now())::BIGINT)", sql)
        self.assertNotIn("DROP POLICY", sql.upper())
        self.assertNotIn("DISABLE ROW LEVEL SECURITY", sql.upper())


if __name__ == "__main__":
    unittest.main()
