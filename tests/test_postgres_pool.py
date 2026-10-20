"""Regression tests for bounded PostgreSQL connection pooling."""
import unittest
from unittest.mock import MagicMock, patch

import backend.postgres as postgres


class FakePool:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.open_calls = []
        self.connection = MagicMock()
        self.getconn_calls = []
        self.__class__.instances.append(self)

    @staticmethod
    def check_connection(connection):
        return None

    def open(self, *, wait, timeout):
        self.open_calls.append((wait, timeout))

    def getconn(self, *, timeout):
        self.getconn_calls.append(timeout)
        return self.connection


class PostgresPoolTests(unittest.TestCase):
    def setUp(self):
        self.old_pools = postgres._POOLS.copy()
        postgres._POOLS.clear()
        FakePool.instances.clear()

    def tearDown(self):
        postgres._POOLS.clear()
        postgres._POOLS.update(self.old_pools)

    def test_pool_is_reused_and_separated_by_connection_config(self):
        with patch.object(postgres, "ConnectionPool", FakePool):
            first = postgres._pool_for("postgresql://user:secret-a@localhost/db", "require")
            again = postgres._pool_for("postgresql://user:secret-a@localhost/db", "require")
            second = postgres._pool_for("postgresql://user:secret-b@localhost/db", "require")

        self.assertIs(first, again)
        self.assertIsNot(first, second)
        self.assertEqual(len(FakePool.instances), 2)
        kwargs = FakePool.instances[0].kwargs
        self.assertEqual(kwargs["min_size"], 1)
        self.assertEqual(kwargs["max_size"], 4)
        self.assertEqual(kwargs["max_waiting"], 12)
        self.assertTrue(kwargs["close_returns"])
        self.assertTrue(callable(kwargs["check"]))
        self.assertEqual(FakePool.instances[0].open_calls, [(True, 5.0)])

    def test_pool_checkout_uses_bounded_timeout(self):
        with patch.object(postgres, "ConnectionPool", FakePool):
            pool = postgres._pool_for("postgresql://user:secret@localhost/db", "require")
            connection = pool.getconn(timeout=4.0)
        self.assertIs(connection, FakePool.instances[0].connection)
        self.assertEqual(FakePool.instances[0].getconn_calls, [4.0])

    def test_each_pooled_connection_return_is_closed_through_pool_api(self):
        fake_pool = MagicMock()
        raw = MagicMock()
        fake_pool.getconn.return_value = raw
        env = {
            "DATABASE_URL": "postgresql://user:secret@localhost/db",
            "SMETRA_DB_SCHEMA": "smetra",
            "VERCEL_ENV": "production",
            "SMETRA_LOCAL_POSTGRES": "1",
        }
        with patch.dict("os.environ", env), patch.object(
            postgres, "_pool_for", return_value=fake_pool
        ):
            connection = postgres.Connection()
            self.assertIs(connection.raw, raw)
            connection.close()
        raw.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
