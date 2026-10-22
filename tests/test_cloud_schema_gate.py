import os
import unittest
from unittest.mock import patch

from backend import app


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parameters=None):
        self.calls.append((sql, parameters))
        return _Result(self.row)


class CloudSchemaGateTests(unittest.TestCase):
    def test_cloud_startup_requires_current_schema_version(self):
        connection = _Connection((app.REQUIRED_CLOUD_SCHEMA_VERSION,))
        with (
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://example.invalid/smetra"}),
            patch.object(app, "db", return_value=connection),
        ):
            app.migrate()

        self.assertEqual(connection.calls[0][1], (app.REQUIRED_CLOUD_SCHEMA_VERSION,))

    def test_cloud_startup_rejects_older_schema(self):
        connection = _Connection(None)
        with (
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://example.invalid/smetra"}),
            patch.object(app, "db", return_value=connection),
            self.assertRaisesRegex(RuntimeError, f"version {app.REQUIRED_CLOUD_SCHEMA_VERSION}"),
        ):
            app.migrate()


if __name__ == "__main__":
    unittest.main()
