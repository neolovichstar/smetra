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
    def test_vercel_never_creates_a_disconnected_sqlite_database(self):
        # Missing or accidentally removed DATABASE_URL must not create
        # serverless-local user state, even during a successful cold start.
        for markers in ({"VERCEL": "1"}, {"VERCEL_ENV": "preview"}):
            with self.subTest(markers=markers):
                env = {"DATABASE_URL": "", "VERCEL": "", "VERCEL_ENV": ""}
                env.update(markers)
                with (
                    patch.dict(os.environ, env),
                    patch.object(app.DB_PATH.parent.__class__, "mkdir") as mkdir,
                    self.assertRaisesRegex(RuntimeError, "Cloud PostgreSQL is not configured"),
                ):
                    with app.db():
                        self.fail("Cloud must not enter a local SQLite context")
                mkdir.assert_not_called()

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
