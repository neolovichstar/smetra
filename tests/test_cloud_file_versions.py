"""Regression tests for cloud content versioning and obsolete work."""
import json
import sqlite3
import unittest
from unittest.mock import patch

from backend import cloud_drives


def db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE cloud_connections(
      id TEXT PRIMARY KEY, workspace_id TEXT, status TEXT, provider TEXT,
      last_synced_at INTEGER, last_error TEXT, updated_at INTEGER);
    CREATE TABLE cloud_files(
      id TEXT PRIMARY KEY, workspace_id TEXT, binding_id TEXT, connection_id TEXT,
      provider_file_id TEXT, parent_folder_id TEXT, name TEXT, mime TEXT,
      provider_mime TEXT, size INTEGER, modified_at TEXT, source_fingerprint TEXT,
      web_view_url TEXT, trashed INTEGER, processing_status TEXT, last_error TEXT,
      first_seen_at INTEGER, updated_at INTEGER,
      UNIQUE(connection_id, provider_file_id));
    CREATE TABLE document_processing_jobs(
      id TEXT PRIMARY KEY,workspace_id TEXT,cloud_file_id TEXT,
      source_fingerprint TEXT,status TEXT,next_attempt_at INTEGER,
      progress TEXT DEFAULT 'В очереди',error TEXT DEFAULT '',attempts INTEGER DEFAULT 0,
      lease_token TEXT DEFAULT '',lease_until INTEGER DEFAULT 0,
      extraction TEXT DEFAULT '{}',proposal TEXT DEFAULT '{}',
      created_at INTEGER,updated_at INTEGER,
      UNIQUE(cloud_file_id,source_fingerprint));
    CREATE TABLE cloud_folder_bindings(
      id TEXT PRIMARY KEY,last_synced_at INTEGER,next_sync_at INTEGER,
      sync_requested INTEGER,last_error TEXT,updated_at INTEGER);
    INSERT INTO cloud_connections(id,workspace_id,status,provider)
      VALUES('conn-a','workspace-a','active','yandex_disk');
    INSERT INTO cloud_folder_bindings(id) VALUES('binding-a');
    """)
    return con


def entry(date, size=200, resource_id="stable-object-id"):
    # Provider UUID is stable across writes; modified date changes.
    with patch("backend.cloud_drives._yandex_api", return_value={
        "_embedded": {"items": [{
            "path": "disk:/docs/bill.pdf", "name": "bill.pdf", "type": "file",
            "mime_type": "application/pdf", "size": size, "modified": date,
            "resource_id": resource_id, "file": "https://cloud-api.yandex.net/preview",
        }], "total": 1}
    }):
        files = cloud_drives._yandex_files(None, {"provider":"yandex_disk"}, "/docs", False)
    assert len(files) == 1
    return files[0]


class YandexContentVersionTests(unittest.TestCase):
    def setUp(self):
        access = patch("backend.cloud_drives._worker_access")
        access.start()
        self.addCleanup(access.stop)

    def test_same_resource_id_new_modified_or_size_changes_fingerprint(self):
        first=entry("2026-10-28T08:00:00+00:00")
        updated=entry("2026-10-28T09:00:00+00:00")
        resized=entry("2026-10-28T08:00:00+00:00", 201)
        self.assertEqual(first["legacy_fingerprint"], updated["legacy_fingerprint"])
        self.assertNotEqual(first["fingerprint"], updated["fingerprint"])
        self.assertNotEqual(first["fingerprint"], resized["fingerprint"])

    def test_legacy_file_does_not_trigger_unnecessary_reimport_then_edit_does(self):
        con=db()
        old=entry("2026-10-28T08:00:00+00:00")
        con.execute("""
            INSERT INTO cloud_files(id,workspace_id,binding_id,connection_id,
              provider_file_id,parent_folder_id,name,mime,provider_mime,size,modified_at,
              source_fingerprint,web_view_url,trashed,processing_status,last_error,
              first_seen_at,updated_at)
            VALUES('old-file','workspace-a','binding-a','conn-a',?,?,?,?,?,?,?,?,?,0,'processed','',1,1)
        """, (old["provider_file_id"], old["parent_folder_id"],old["name"],
               old["mime"],old["provider_mime"],old["size"],old["modified_at"],
               old["legacy_fingerprint"],old["web_view_url"]))
        binding={"id":"binding-a","workspace_id":"workspace-a","connection_id":"conn-a",
                 "folder_id":"/docs","recursive":0}
        try:
            with patch("backend.cloud_drives._yandex_files",return_value=[old]):
                self.assertEqual(cloud_drives._sync_binding(con,binding),1)
            after=con.execute("SELECT source_fingerprint,processing_status FROM cloud_files").fetchone()
            self.assertEqual(after["source_fingerprint"],old["legacy_fingerprint"])
            self.assertEqual(after["processing_status"],"processed")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM document_processing_jobs").fetchone()[0],0)

            changed=entry("2026-10-28T09:00:00+00:00")
            with patch("backend.cloud_drives._yandex_files",return_value=[changed]):
                self.assertEqual(cloud_drives._sync_binding(con,binding),1)
            after=con.execute("SELECT source_fingerprint,processing_status FROM cloud_files").fetchone()
            self.assertEqual(after["source_fingerprint"],changed["fingerprint"])
            self.assertEqual(after["processing_status"],"queued")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM document_processing_jobs").fetchone()[0],1)

            # The next hourly/daily poll must NOT schedule the same revision again.
            with patch("backend.cloud_drives._yandex_files",return_value=[changed]):
                self.assertEqual(cloud_drives._sync_binding(con,binding),1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM document_processing_jobs").fetchone()[0],1)
        finally:
            con.close()


class CloudDownloadTests(unittest.TestCase):
    class FakeDownload:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return self.body

    def test_google_native_document_exports_pdf_without_exposing_download_url(self):
        connection = {"provider": "google_drive"}
        file = {"size": 1, "provider_file_id": "google-file-1",
                "provider_mime": "application/vnd.google-apps.document"}
        with patch("backend.cloud_drives._access_token", return_value="test-token"), patch(
            "backend.cloud_drives._safe_download_open",
            return_value=self.FakeDownload(b"%PDF-synthetic-document")
        ) as opener:
            raw = cloud_drives._download(None, connection, file)
        self.assertEqual(raw, b"%PDF-synthetic-document")
        req = opener.call_args.args[0]
        self.assertIn("/files/google-file-1/export?mimeType=application/pdf", req.full_url)
        self.assertEqual(req.get_header("Authorization"), "Bearer test-token")

    def test_google_download_is_bounded_even_when_provider_misreports_size(self):
        file = {"size": 10, "provider_file_id": "file-2",
                "provider_mime": "application/pdf"}
        with patch("backend.cloud_drives._access_token", return_value="test-token"), patch(
            "backend.cloud_drives._safe_download_open",
            return_value=self.FakeDownload(b"x" * (cloud_drives.MAX_FILE_BYTES + 1))
        ):
            with self.assertRaises(cloud_drives.business.DomainError) as raised:
                cloud_drives._download(None, {"provider": "google_drive"}, file)
        self.assertEqual(raised.exception.status, 413)

    def test_yandex_signed_download_never_reuses_oauth_access_token(self):
        signed = "https://downloader.disk.yandex.net/signed-file"
        file = {"size": 30, "provider_file_id": "disk:/docs/bill.pdf"}
        with (
            patch("backend.cloud_drives._access_token", return_value="test-oauth-token"),
            patch("backend.cloud_drives._yandex_api", return_value={"href": signed}),
            patch("backend.cloud_drives._safe_cloud_href", return_value=True),
            patch("backend.cloud_drives._safe_download_open",
                  return_value=self.FakeDownload(b"%PDF-yandex-test")) as opener,
        ):
            raw = cloud_drives._download(None, {"provider": "yandex_disk"}, file)
        self.assertEqual(raw, b"%PDF-yandex-test")
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, signed)
        self.assertIsNone(request.get_header("Authorization"))

    def test_yandex_rejects_untrusted_signed_download_url(self):
        file = {"size": 10, "provider_file_id": "disk:/docs/bill.pdf"}
        with (
            patch("backend.cloud_drives._access_token", return_value="test-token"),
            patch("backend.cloud_drives._yandex_api",
                  return_value={"href": "http://127.0.0.1/internal"}),
            patch("backend.cloud_drives._safe_download_open") as opener,
        ):
            with self.assertRaises(cloud_drives.business.DomainError) as raised:
                cloud_drives._download(None, {"provider": "yandex_disk"}, file)
        self.assertEqual(raised.exception.status, 502)
        opener.assert_not_called()


class CloudDocumentModelSafetyTests(unittest.TestCase):
    def test_model_invalid_confidence_does_not_break_extraction(self):
        body={"choices":[{"message":{"content":json.dumps({
            "document_type":"invoice","merchant":"Supplier",
            "confidence":"not a number",
            "items":[{"name":"paint","quantity":"2","unit_price_kopecks":1200}]
        })}}]}
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,limit):return json.dumps(body).encode()
        with patch.dict("os.environ",{"OPENROUTER_API_KEY":"testing","OPENROUTER_DOC_MODEL":"fake-model"}),patch(
            "backend.file_processing.isolated_extract",return_value={"pages":[[1,"Invoice 2 paint"]] }
        ), patch("backend.cloud_drives.urllib.request.urlopen",return_value=FakeResponse()):
            value=cloud_drives._model_extract("application/pdf","bill.pdf",b"%PDF-test")
        self.assertEqual(value["confidence"],0.0)
        self.assertTrue(value["needs_confirmation"])
        self.assertEqual(value["items"][0]["unit_price_kopecks"],1200)


if __name__=="__main__":
    unittest.main()
