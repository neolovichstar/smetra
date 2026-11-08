"""Capacity failures stay bounded, retryable, and do not weaken DB TLS."""
import http.client
import json
import unittest
from unittest.mock import Mock, patch

from psycopg_pool import PoolTimeout, TooManyRequests
from backend import postgres
from backend.service_errors import DatabaseBusyError
from tests import test_business


class DatabaseCapacityTests(unittest.TestCase):
    def test_pool_queue_is_finite_even_for_bad_configuration(self):
        for value, expected in (("16", 16), ("0", 1), ("99999", 256), ("bad", 16)):
            with self.subTest(value=value), patch.dict(
                "os.environ", SMETRA_DB_POOL_MAX_WAITING=value
            ), patch.dict(postgres._POOLS, {}, clear=True), patch.object(
                postgres, "ConnectionPool"
            ) as factory:
                postgres._connection_pool("postgresql://example.invalid/db", False)
                self.assertEqual(factory.call_args.kwargs["max_waiting"], expected)
                self.assertLessEqual(factory.call_args.kwargs["max_size"], 4)

    def test_verified_tls_is_preserved_in_effective_pool_options(self):
        for mode in ("verify-ca", "verify-full"):
            with self.subTest(mode=mode), patch.dict(postgres._POOLS, {}, clear=True), patch.object(
                postgres, "ConnectionPool"
            ) as factory:
                postgres._connection_pool(
                    "postgresql://db.example.invalid/db?sslmode=" + mode, False
                )
                self.assertEqual(factory.call_args.kwargs["kwargs"]["sslmode"], mode)
        for mode in ("disable", "allow", "prefer", "require"):
            self.assertEqual(postgres._tls_mode("postgresql://remote/db?sslmode=" + mode, False), "require")
        self.assertEqual(postgres._tls_mode("postgresql://localhost/db", True), "disable")

    def test_pool_saturation_becomes_dependency_neutral_busy_error(self):
        for error in (PoolTimeout("pool secret must not escape"), TooManyRequests("queue full")):
            pool = Mock()
            pool.getconn.side_effect = error
            with self.subTest(error=type(error).__name__), patch.dict(
                "os.environ", DATABASE_URL="postgresql://db.example.invalid/db"
            ), patch.object(postgres, "_connection_pool", return_value=pool):
                with self.assertRaises(DatabaseBusyError) as result:
                    postgres.Connection()
                self.assertNotIn("secret", str(result.exception))

    def test_direct_connections_preserve_verified_tls_too(self):
        with patch.dict("os.environ", DATABASE_URL="postgresql://db.example.invalid/db?sslmode=verify-full"), patch.object(
            postgres, "_connection_pool", return_value=None
        ), patch.object(postgres.psycopg, "connect") as connect:
            postgres.Connection().close()
            self.assertEqual(connect.call_args.kwargs["sslmode"], "verify-full")


class BusyHttpTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)

    def test_saturated_api_returns_retryable_503_without_internal_details(self):
        with patch.object(self.mod, "db", side_effect=DatabaseBusyError("private connection details")):
            connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
            connection.request("GET", "/api/me")
            response = connection.getresponse()
            body = json.loads(response.read())
            self.assertEqual(response.status, 503)
            self.assertEqual(response.getheader("Retry-After"), "2")
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertEqual(body["code"], "service_busy")
            self.assertNotIn("private", str(body))
            connection.close()
        self.assertEqual(self.call("/me")[0], 401, "The next request recovers normally")

    call = test_business.BusinessFlows.call
