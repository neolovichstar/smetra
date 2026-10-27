"""Backup safety boundaries and a real restore drill on disposable PostgreSQL."""
import hashlib
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
from psycopg import sql
from backend import postgres_backup as backups


class BackupSafetyTests(unittest.TestCase):
    def test_restore_never_connects_to_production_or_the_source_database(self):
        urls = [
            "postgresql://user:private@db.example.invalid/smetra_restore_test",
            "postgresql://user:private@localhost/smetra_test",
            "postgresql://user:private@localhost/smetra_restore_test?host=db.example.invalid",
            "postgresql://user:private@localhost/smetra_restore_test?dbname=postgres",
            "postgresql://user:private@localhost/smetra_restore_test?hostaddr=203.0.113.1",
        ]
        with patch.object(backups, "_connect", side_effect=AssertionError("Must not connect")):
            for url in urls:
                with self.subTest(url=url), self.assertRaises(backups.BackupError):
                    backups.restore_check("missing.dump", url)

    def test_damaged_dump_and_invalid_manifest_are_rejected_before_connecting(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "fixture.dump"
            archive.write_bytes(b"fixture")
            manifest = Path(str(archive) + ".json")
            manifest.write_text(json.dumps({"format": "smetra-postgres-backup-v1", "schema": "smetra",
                                             "dump_sha256": "0" * 64, "inventory": {}}))
            with patch.object(backups, "_connect", side_effect=AssertionError("Must not connect")):
                with self.assertRaises(backups.BackupError):
                    backups.restore_check(archive, "postgresql://localhost/smetra_restore_test")
                value = json.loads(manifest.read_text())
                value["dump_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
                manifest.write_text(json.dumps(value))
                with self.assertRaises(backups.BackupError):
                    backups.restore_check(archive, "postgresql://localhost/smetra_restore_test")

    def test_existing_backup_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "existing.dump"
            destination.write_bytes(b"keep this")
            with patch.object(backups, "_connect", side_effect=AssertionError("Must not connect")), \
                    self.assertRaises(backups.BackupError):
                backups.backup("postgresql://localhost/smetra_test", destination)
            self.assertEqual(destination.read_bytes(), b"keep this")

    def test_credentials_never_enter_subprocess_arguments_or_failure_messages(self):
        url = "postgresql://user:never-log-this@localhost/smetra_test?sslmode=require"
        with patch.object(backups.shutil, "which", return_value="/usr/bin/pg_dump"), \
                patch.object(backups.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr=b"never-log-this")) as process, \
                self.assertRaises(backups.BackupError) as raised:
            backups._run(["pg_dump", "--no-password"], url)
        self.assertNotIn("never-log-this", str(raised.exception))
        self.assertNotIn("never-log-this", repr(process.call_args.args))
        self.assertEqual(process.call_args.kwargs["env"]["PGSSLMODE"], "require")
        self.assertEqual(process.call_args.kwargs["env"]["PGPASSWORD"], "never-log-this")

    def test_schema_patterns_are_not_accepted(self):
        with patch.object(backups, "_connect", side_effect=AssertionError("Must not connect")):
            for schema in ("*", "smetra; DROP SCHEMA smetra", "smetra,public", ""):
                with self.subTest(schema=schema), self.assertRaises(backups.BackupError):
                    backups.check("postgresql://localhost/smetra_test", schema)


@unittest.skipUnless(os.getenv("SMETRA_TEST_FULL_POSTGRES") == "1" and os.getenv("SMETRA_TEST_ADMIN_URL")
                     and shutil.which("pg_dump") and shutil.which("pg_restore"),
                     "requires PostgreSQL client tools and the full disposable fixture")
class PostgresRestoreDrillTests(unittest.TestCase):
    def test_restore_verifies_data_and_rls_then_refuses_to_overwrite_the_target(self):
        from scripts.prepare_test_postgres import PLATFORM, validate_target

        source = os.environ["SMETRA_TEST_ADMIN_URL"]
        validate_target(source)
        target_name = "smetra_restore_" + uuid.uuid4().hex
        parsed = urllib.parse.urlsplit(source)
        query = urllib.parse.urlencode([(key, value) for key, value in urllib.parse.parse_qsl(parsed.query)
                                        if key != "dbname"])
        target = urllib.parse.urlunsplit(parsed._replace(path="/" + target_name, query=query))
        with psycopg.connect(source, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_name)))
        try:
            with psycopg.connect(target, autocommit=True) as con:
                con.execute(PLATFORM)
            with tempfile.TemporaryDirectory() as folder:
                archive = Path(folder) / "application.dump"
                saved = backups.backup(source, archive)
                self.assertGreater(saved["tables"], 100)
                if os.name != "nt":
                    self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(Path(str(archive) + ".json").stat().st_mode & 0o777, 0o600)
                recovered = backups.restore_check(archive, target)
                self.assertTrue(recovered["ok"])
                self.assertEqual(recovered["tables"], saved["tables"])
                self.assertIn("row_contents", recovered["verified"])
                with self.assertRaises(backups.BackupError):
                    backups.restore_check(archive, target)
                with psycopg.connect(target) as con:
                    self.assertEqual(con.execute("SELECT max(version) FROM smetra.schema_migrations").fetchone()[0], 67)
        finally:
            with psycopg.connect(source, autocommit=True) as admin:
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(target_name)))
