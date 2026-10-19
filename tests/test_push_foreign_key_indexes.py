"""Regression coverage for indexes on the active push-queue foreign keys."""
from pathlib import Path
import sqlite3
import unittest


ROOT = Path(__file__).resolve().parents[1]
SQLITE_MIGRATION = ROOT / "backend" / "migrations" / "024_push_foreign_key_indexes.sql"
POSTGRES_MIGRATION = (
    ROOT / "supabase" / "migrations" / "20261019162437_push_foreign_key_indexes.sql"
)

EXPECTED_INDEXES = {
    "idx_push_outbox_workspace_id": ("push_outbox", ("workspace_id",)),
    "idx_push_outbox_notification_id": ("push_outbox", ("notification_id",)),
    "idx_push_deliveries_workspace_id": ("push_deliveries", ("workspace_id",)),
    "idx_push_deliveries_device_id": ("push_deliveries", ("device_id",)),
}


class PushForeignKeyIndexTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at INTEGER NOT NULL
            );
            CREATE TABLE push_outbox (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                notification_id TEXT NOT NULL,
                sent_at INTEGER,
                next_attempt_at INTEGER NOT NULL
            );
            CREATE TABLE push_deliveries (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                outbox_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                completed_at INTEGER,
                next_attempt_at INTEGER NOT NULL,
                UNIQUE(outbox_id, device_id)
            );
            """
        )

    def tearDown(self):
        self.con.close()

    def apply_sqlite_migration(self):
        self.con.executescript(SQLITE_MIGRATION.read_text(encoding="utf-8"))

    def test_sqlite_migration_creates_exact_foreign_key_indexes(self):
        self.apply_sqlite_migration()
        names = {
            row[0]
            for row in self.con.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        for name, (table, columns) in EXPECTED_INDEXES.items():
            with self.subTest(index=name):
                self.assertIn(name, names)
                actual_columns = tuple(
                    row[2] for row in self.con.execute(f"PRAGMA index_info('{name}')")
                )
                self.assertEqual(actual_columns, columns)

        applied = self.con.execute(
            "SELECT applied_at FROM schema_migrations WHERE version=34"
        ).fetchone()
        self.assertIsNotNone(applied)

    def test_hot_path_lookup_plans_use_the_new_indexes(self):
        self.apply_sqlite_migration()
        lookups = (
            ("SELECT * FROM push_outbox WHERE workspace_id = ?", "idx_push_outbox_workspace_id"),
            ("SELECT * FROM push_outbox WHERE notification_id = ?", "idx_push_outbox_notification_id"),
            ("SELECT * FROM push_deliveries WHERE workspace_id = ?", "idx_push_deliveries_workspace_id"),
            ("SELECT * FROM push_deliveries WHERE device_id = ?", "idx_push_deliveries_device_id"),
        )
        for sql, expected_index in lookups:
            with self.subTest(index=expected_index):
                plan = "\n".join(
                    str(row[3])
                    for row in self.con.execute("EXPLAIN QUERY PLAN " + sql, ("test",))
                )
                self.assertIn(expected_index, plan)

    def test_postgres_migration_matches_sqlite_indexes_and_is_bounded(self):
        sql = POSTGRES_MIGRATION.read_text(encoding="utf-8")
        for name in EXPECTED_INDEXES:
            with self.subTest(index=name):
                self.assertIn(f"CREATE INDEX IF NOT EXISTS {name}", sql)
        self.assertIn("SET LOCAL lock_timeout='5s'", sql)
        self.assertIn("SET LOCAL statement_timeout='30s'", sql)
        self.assertIn("VALUES (34, extract(epoch FROM now())::BIGINT)", sql)


if __name__ == "__main__":
    unittest.main()
