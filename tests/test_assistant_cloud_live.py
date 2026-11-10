"""Cloud provider search requires no folder bindings or payload storage."""
import os
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet

from backend import assistant_cloud, assistant_cloud_live, business


PDF_FILE = {
    "id": "Google_ABC-42", "name": "Дом на набережной.pdf",
    "mimeType": "application/pdf", "size": "52000000",
}


class LiveCloudSearchTests(unittest.TestCase):
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
                provider_mime TEXT, updated_at INTEGER, trashed INTEGER
            );
            INSERT INTO cloud_connections
                VALUES ('google','ws','u','active','google_drive','Konstantin',1);
        """)
        self.service = SimpleNamespace(
            con=self.con, wid="ws", role="owner", user={"id": "u"}
        )
        self.patch_env = patch.dict(os.environ, {
            "CLOUD_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode()
        })
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)
        self.addCleanup(self.con.close)

    @staticmethod
    def google_api(_con, _connection, path, params=None):
        if path == "/files":
            assert params["q"].startswith("trashed = false")
            assert "name contains 'дом'" in params["q"]
            assert "name contains 'набережной'" in params["q"]
            return {"files": [PDF_FILE]}
        if path == "/files/" + PDF_FILE["id"]:
            return dict(PDF_FILE)
        raise AssertionError(path)

    def test_finds_pdf_without_any_bound_folders(self):
        with patch("backend.cloud_drives._premium_access"), patch(
            "backend.cloud_drives._worker_access"
        ), patch("backend.cloud_drives._google_api", side_effect=self.google_api):
            result = assistant_cloud.list_files(self.service, "дом на набережной")
        self.assertEqual(result["connected_accounts_searched"], 1)
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["name"], PDF_FILE["name"])
        self.assertEqual(result["files"][0]["size"], 52000000)
        opaque = result["files"][0]["id"]
        self.assertTrue(opaque.startswith("live."))
        self.assertNotIn("Google_ABC-42", opaque)
        self.assertIsNone(self.con.execute("SELECT * FROM cloud_folder_bindings").fetchone())
        self.assertIsNone(self.con.execute(
            "SELECT name FROM sqlite_master WHERE name='file_payloads'"
        ).fetchone())

    def test_reads_live_pdf_without_saving_source_bytes(self):
        with patch("backend.cloud_drives._premium_access"), patch(
            "backend.cloud_drives._worker_access"
        ), patch("backend.cloud_drives._google_api", side_effect=self.google_api), patch(
            "backend.cloud_drives._download", return_value=b"%PDF-private"
        ) as download, patch(
            "backend.file_processing.isolated_extract",
            return_value={"pages": [[1, "Площадь 52 м2"]], "truncated": False,
                          "next_page": None, "total_pages": 1},
        ) as extractor:
            listed = assistant_cloud.list_files(self.service, "дом на набережной")
            answer = assistant_cloud.read_file(self.service, listed["files"][0]["id"])
        self.assertEqual(answer["excerpts"][0]["text"], "Площадь 52 м2")
        self.assertEqual(answer["excerpts"][0]["page"], 1)
        self.assertEqual(answer["name"], PDF_FILE["name"])
        self.assertEqual(download.call_args.kwargs["max_bytes"], 100_000_000)
        self.assertIn("cloud:application/pdf:1", extractor.call_args.args)
        self.assertIsNone(self.con.execute(
            "SELECT name FROM sqlite_master WHERE name='file_payloads'"
        ).fetchone())

    def test_other_user_cannot_reuse_encrypted_reference(self):
        with patch("backend.cloud_drives._worker_access"), patch(
            "backend.cloud_drives._google_api", side_effect=self.google_api
        ):
            own = assistant_cloud_live.search(self.service, "дом на набережной")
            token = own["files"][0]["id"]
            self.service.user = {"id": "other"}
            with self.assertRaises(business.DomainError) as error:
                assistant_cloud_live.resolve(self.service, token)
            self.assertEqual(error.exception.status, 403)
            self.assertEqual(assistant_cloud_live.search(self.service, "дом")["files"], [])

    def test_disconnected_drive_refused_after_search(self):
        with patch("backend.cloud_drives._worker_access"), patch(
            "backend.cloud_drives._google_api", side_effect=self.google_api
        ):
            opaque = assistant_cloud_live.search(
                self.service, "дом на набережной"
            )["files"][0]["id"]
            self.con.execute("UPDATE cloud_connections SET status='disabled'")
            with self.assertRaises(business.DomainError) as error:
                assistant_cloud_live.resolve(self.service, opaque)
            self.assertEqual(error.exception.status, 403)

    def test_forged_file_reference_is_rejected(self):
        with self.assertRaises(business.DomainError) as error:
            assistant_cloud_live.resolve(self.service, "live.made-up-token")
        self.assertEqual(error.exception.status, 410)

    def test_provider_failure_does_not_masquerade_as_missing_document(self):
        with patch("backend.cloud_drives._worker_access"), patch(
            "backend.cloud_drives._google_api",
            side_effect=business.DomainError(503, "Google API временно недоступен"),
        ):
            result = assistant_cloud_live.search(self.service, "набережной")
        self.assertEqual(result["files"], [])
        self.assertEqual(result["errors"][0]["provider"], "google_drive")
        self.assertIn("временно недоступен", result["errors"][0]["error"])

    def test_size_is_rechecked_before_download(self):
        def api(_con, _connection, path, params=None):
            if path == "/files":
                return {"files": [PDF_FILE]}
            return {**PDF_FILE, "size": "110000000"}
        with patch("backend.cloud_drives._premium_access"), patch(
            "backend.cloud_drives._worker_access"
        ), patch("backend.cloud_drives._google_api", side_effect=api), patch(
            "backend.cloud_drives._download"
        ) as download:
            ref = assistant_cloud.list_files(self.service, "дом")["files"][0]["id"]
            with self.assertRaises(business.DomainError) as error:
                assistant_cloud.read_file(self.service, ref)
        self.assertEqual(error.exception.status, 413)
        download.assert_not_called()

    def test_yandex_search_entire_disk_not_folder(self):
        self.con.execute("UPDATE cloud_connections SET provider='yandex_disk' WHERE id='google'")
        def api(_con, _connection, path, params=None):
            self.assertEqual(path, "/resources/files")
            self.assertNotIn("path", params)
            return {"items": [{"name": "Дом на набережной.pdf",
                               "path": "disk:/design/Дом на набережной.pdf",
                               "size": 1000000, "mime_type": "application/pdf"}]}
        with patch("backend.cloud_drives._worker_access"), patch(
            "backend.cloud_drives._yandex_api", side_effect=api
        ):
            result = assistant_cloud_live.search(self.service, "набережной")
        self.assertEqual(result["files"][0]["provider"], "yandex_disk")
        self.assertTrue(result["files"][0]["id"].startswith("live."))


    def test_cloud_pdf_vision_reads_single_page_without_storage(self):
        import base64
        import io
        import json
        from backend import cloud_drives

        self.service.h = SimpleNamespace(throttle=lambda *_args: None)
        jpeg = b"\\xff\\xd8" + b"tiny-private-page" + b"\\xff\\xd9"
        fake_page = {
            "pages": [[2, base64.b64encode(jpeg).decode()]],
            "total_pages": 4, "truncated": True,
        }
        response = SimpleNamespace(read=lambda _n: json.dumps({
            "choices": [{"message": {"content": "Страница 2: комната 19 м²"}}]
        }, ensure_ascii=False).encode())
        class OpenResponse:
            def __enter__(self): return response
            def __exit__(self, *args): return False

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture-not-real"}), patch(
            "backend.cloud_drives._premium_access"
        ), patch("backend.cloud_drives._worker_access"), patch(
            "backend.cloud_drives._google_api", side_effect=self.google_api
        ), patch("backend.cloud_drives._download", return_value=b"%PDF-secret") as download, patch(
            "backend.file_processing.isolated_extract", return_value=fake_page
        ) as render, patch("urllib.request.urlopen", return_value=OpenResponse()) as completion:
            result = assistant_cloud.list_files(self.service, "дом на набережной")
            analysis = assistant_cloud.analyze_page(
                self.service, result["files"][0]["id"], page_number=2,
            )
        self.assertEqual(analysis["page"], 2)
        self.assertEqual(analysis["total_pages"], 4)
        self.assertIn("комната 19", analysis["analysis"])
        self.assertFalse(analysis["source_stored"])
        self.assertEqual(download.call_args.kwargs["max_bytes"], 100_000_000)
        self.assertEqual(render.call_args.args[1], "cloud-render-pdf:2")
        payload = json.loads(completion.call_args.args[0].data)
        self.assertEqual(payload["provider"]["data_collection"], "deny")
        self.assertEqual(payload["messages"][-1]["content"][-1]["type"], "image_url")
        self.assertTrue(payload["messages"][-1]["content"][-1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertIsNone(self.con.execute(
            "SELECT name FROM sqlite_master WHERE name='file_payloads'"
        ).fetchone())

    def test_cloud_pdf_vision_rejects_incorrect_page_image(self):
        import base64
        self.service.h = SimpleNamespace(throttle=lambda *_args: None)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture-not-real"}), patch(
            "backend.cloud_drives._premium_access"
        ), patch("backend.cloud_drives._worker_access"), patch(
            "backend.cloud_drives._google_api", side_effect=self.google_api
        ), patch("backend.cloud_drives._download", return_value=b"%PDF-secret"), patch(
            "backend.file_processing.isolated_extract", return_value={
                "pages": [[1, base64.b64encode(b"not jpeg").decode()]], "total_pages": 4
            }
        ), patch("urllib.request.urlopen") as network:
            item = assistant_cloud.list_files(self.service, "дом")["files"][0]
            with self.assertRaises(business.DomainError) as error:
                assistant_cloud.analyze_page(self.service, item["id"], page_number=1)
            self.assertEqual(error.exception.status, 422)
            network.assert_not_called()

    def test_cloud_pdf_renderer_can_read_second_page_in_isolated_process(self):
        import io
        from pypdf import PdfWriter
        from backend.file_processing import isolated_extract

        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=595, height=842)
        file = io.BytesIO()
        writer.write(file)
        rendered = isolated_extract(file.getvalue(), "cloud-render-pdf:2")
        self.assertEqual(rendered["total_pages"], 3)
        self.assertEqual(rendered["pages"][0][0], 2)
        self.assertEqual(len(rendered["pages"]), 1)


if __name__ == "__main__":
    unittest.main()
