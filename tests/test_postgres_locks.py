"""Tests for tenant-scoped PostgreSQL write serialization."""
import unittest

from backend.postgres import Connection


class FakeRaw:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self


def make_connection(runtime):
    connection = Connection.__new__(Connection)
    connection.schema = "smetra"
    connection.runtime = runtime
    connection.scoped = False
    connection.nested = False
    connection.workspace_lock_key = None
    connection.lock_key = 101
    connection.raw = FakeRaw()
    return connection


class PostgresWriteLockTests(unittest.TestCase):
    def test_runtime_writes_take_shared_global_then_workspace_lock(self):
        connection = make_connection(runtime=True)
        connection.scope("session-hash", "workspace-a")
        workspace_lock = connection.workspace_lock_key
        connection.execute("BEGIN IMMEDIATE")

        statements = [sql for sql, _ in connection.raw.calls]
        shared_global = "SELECT pg_advisory_xact_lock_shared(%s)"
        exclusive_workspace = "SELECT pg_advisory_xact_lock(%s)"
        self.assertIn(shared_global, statements)
        self.assertIn(exclusive_workspace, statements)
        self.assertLess(statements.index(shared_global), statements.index(exclusive_workspace))
        self.assertNotEqual(workspace_lock, connection.lock_key)
        self.assertEqual(connection.raw.calls[statements.index(exclusive_workspace)][1], (workspace_lock,))

    def test_distinct_workspaces_get_distinct_serialization_keys(self):
        first = make_connection(runtime=True)
        second = make_connection(runtime=True)
        first.scope("session-a", "workspace-a")
        second.scope("session-b", "workspace-b")
        self.assertNotEqual(first.workspace_lock_key, second.workspace_lock_key)
        self.assertEqual(first.lock_key, second.lock_key)

    def test_global_transactions_keep_exclusive_schema_lock(self):
        connection = make_connection(runtime=False)
        connection.execute("BEGIN IMMEDIATE")
        locks = [
            (sql, params)
            for sql, params in connection.raw.calls
            if "pg_advisory_xact_lock" in sql
        ]
        self.assertEqual(locks, [("SELECT pg_advisory_xact_lock(%s)", (connection.lock_key,))])
        self.assertFalse(connection.nested)


if __name__ == "__main__":
    unittest.main()
