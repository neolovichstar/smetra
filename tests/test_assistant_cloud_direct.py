"""Regression tests for cloud-only assistant reads (no source payload persistence)."""
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend import assistant_cloud, business


class CloudReadTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
        CREATE TABLE cloud_connections (
            id TEXT, workspace_id TEXT, user_id TEXT, status TEXT,
            provider TEXT, account_label TEXT, updated_at INTEGER
        );
        CREATE TABLE cloud_folder_bindings (
            id TEXT, workspace_id TEXT, status TEXT, folder_name TEXT
        );
        CREATE TABLE cloud_files (
            id TEXT, workspace_id TEXT, binding_id TEXT, connection_id TEXT,
            name TEXT, mime TEXT, size INTEGER, provider_file_id TEXT,
            provider_mime TEXT, source_fingerprint TEXT,
            updated_at INTEGER, trashed INTEGER
        );
        INSERT INTO cloud_connections VALUES ('c','w','u','active','google_drive','Test',1);
        INSERT INTO cloud_folder_bindings VALUES ('b','w','active','Проекты');
        INSERT INTO cloud_files VALUES (
            'f','w','b','c','Дизайн проект.pdf','application/pdf',
            52000000,'google-file-id','application/pdf','hash',1,0
        );
        """)
        self.service = SimpleNamespace(con=self.con, wid="w", role="owner", user={"id":"u"})

    def tearDown(self):
        self.con.close()

    def test_lists_only_linked_workspace_files_without_tokens(self):
        with patch("backend.cloud_drives._premium_access"), patch(
            "backend.cloud_drives._worker_access"
        ), patch("backend.cloud_drives._google_api", return_value={"files": []}):
            result = assistant_cloud.list_files(self.service)
        self.assertEqual(result["files"][0]["id"], "f")
        self.assertNotIn("provider_file_id", result["files"][0])
        self.con.execute("UPDATE cloud_folder_bindings SET status='disabled' WHERE id='b'")
        with patch("backend.cloud_drives._premium_access"), patch(
            "backend.cloud_drives._worker_access"
        ), patch("backend.cloud_drives._google_api", return_value={"files": []}):
            self.assertEqual(assistant_cloud.list_files(self.service)["files"], [])

    def test_reads_52mb_pdf_transiently_and_cites_page(self):
        with patch("backend.cloud_drives._premium_access"), patch(
            "backend.cloud_drives._worker_access"
        ), patch(
            "backend.cloud_drives._download", return_value=b"%PDF-fake-source"
        ) as download, patch(
            "backend.file_processing.isolated_extract",
            return_value={"pages": [[1, "Жилая комната 19 м2"], [2, "Площадь 52 м2"]], "truncated": True}
        ) as extractor:
            result = assistant_cloud.read_file(self.service, "f")
        self.assertEqual(result["name"], "Дизайн проект.pdf")
        self.assertEqual(result["excerpts"][0]["page"], 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["pages_scanned"], 2)
        self.assertIn("cloud:application/pdf:1", extractor.call_args.args)
        self.assertEqual(download.call_args.kwargs["max_bytes"], 100_000_000)
        # None of the upload tables or file vault are even present in the test DB.
        self.assertIsNone(self.con.execute(
            "SELECT name FROM sqlite_master WHERE name='file_payloads'"
        ).fetchone())

    def test_can_request_later_page_windows(self):
        with patch("backend.cloud_drives._premium_access"), patch(
            "backend.cloud_drives._worker_access"
        ), patch(
            "backend.cloud_drives._download", return_value=b"%PDF-data"
        ), patch(
            "backend.file_processing.isolated_extract",
            return_value={"pages": [[13, "Страница 13, ведомость работ"]],
                          "truncated": True, "total_pages": 14, "next_page": 14}
        ) as extractor:
            result = assistant_cloud.read_file(self.service, "f", page_start=13)
        self.assertEqual(result["page_start"], 13)
        self.assertEqual(result["total_pages"], 14)
        self.assertEqual(result["next_page"], 14)
        self.assertIn("cloud:application/pdf:13", extractor.call_args.args)

    def test_refuses_unlinked_or_cross_workspace_file(self):
        with patch("backend.cloud_drives._premium_access"), patch("backend.cloud_drives._download") as download:
            self.service.wid = "another"
            with self.assertRaises(business.DomainError) as error:
                assistant_cloud.read_file(self.service, "f")
            self.assertEqual(error.exception.status, 404)
            download.assert_not_called()

    def test_members_cannot_read_team_cloud_directly(self):
        self.service.role = "member"
        with patch("backend.cloud_drives._premium_access"):
            with self.assertRaises(business.DomainError) as error:
                assistant_cloud.read_file(self.service, "f")
            self.assertEqual(error.exception.status, 403)

    def test_pdf_limit_rejects_before_network(self):
        self.con.execute("UPDATE cloud_files SET size=100000001 WHERE id='f'")
        with patch("backend.cloud_drives._premium_access"), patch(
            "backend.cloud_drives._worker_access"
        ), patch("backend.cloud_drives._download") as download:
            with self.assertRaises(business.DomainError) as error:
                assistant_cloud.read_file(self.service, "f")
            self.assertEqual(error.exception.status, 413)
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
