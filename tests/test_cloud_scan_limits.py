"""Bounded cloud scans and signed Yandex URL privacy regression tests."""
import sqlite3
import unittest
from unittest.mock import Mock, patch

from backend import business, cloud_drives


def gf(i):
    return {"id":f"g-{i}","name":f"bill{i}.pdf","mimeType":"application/pdf",
            "size":"100","modifiedTime":"2026-10-28T10:00:00Z"}


def yf(i):
    return {"path":f"disk:/work/{i}.pdf","name":f"{i}.pdf",
            "type":"file","mime_type":"application/pdf","size":100,
            "modified":"2026-10-28T10:00:00Z",
            "file":"https://files.example.invalid/download?sig=test-only"}


class CloudScanLimitsTests(unittest.TestCase):
    def test_google_pagination_complete(self):
        calls=[]
        def api(_con,_connection,_path,params):
            calls.append(params.get("pageToken",""))
            if not params.get("pageToken"):
                return {"files":[gf(i) for i in range(1000)],"nextPageToken":"page-2"}
            return {"files":[gf(i) for i in range(1000,1200)]}
        with patch("backend.cloud_drives._google_api",side_effect=api):
            items=cloud_drives._google_files(None,{},"root",False)
        self.assertEqual(len(items),1200)
        self.assertEqual(calls,["","page-2"])

    def test_google_file_cap_is_an_error_not_partial_success(self):
        def api(_con,_connection,_path,params):
            if not params.get("pageToken"):
                return {"files":[gf(i) for i in range(1000)],"nextPageToken":"more"}
            return {"files":[gf(i) for i in range(1000,1501)]}
        with patch("backend.cloud_drives._google_api",side_effect=api):
            with self.assertRaises(business.DomainError) as context:
                cloud_drives._google_files(None,{},"root",False)
        self.assertEqual(context.exception.status,422)

    def test_google_repeated_page_token_is_error(self):
        with patch("backend.cloud_drives._google_api",
                   return_value={"files":[],"nextPageToken":"repeat"}):
            with self.assertRaises(business.DomainError) as context:
                cloud_drives._google_files(None,{},"root",False)
        self.assertEqual(context.exception.status,502)

    def test_google_request_budget(self):
        def api(_con,_connection,_path,params):
            return {"files":[],"nextPageToken":str(int(params.get("pageToken","0"))+1)}
        with patch("backend.cloud_drives.MAX_SCAN_REQUESTS",5),patch(
            "backend.cloud_drives._google_api",side_effect=api
        ) as remote:
            with self.assertRaises(business.DomainError) as context:
                cloud_drives._google_files(None,{},"root",False)
        self.assertEqual(context.exception.status,503)
        self.assertEqual(remote.call_count,5)

    def test_google_time_budget(self):
        with patch("backend.cloud_drives.time.monotonic",side_effect=[100,132]),patch(
            "backend.cloud_drives._google_api"
        ) as remote:
            with self.assertRaises(business.DomainError) as context:
                cloud_drives._google_files(None,{},"root",False)
        self.assertEqual(context.exception.status,503)
        remote.assert_not_called()

    def test_yandex_pages_and_no_signed_urls(self):
        def api(_con,_connection,_path,params):
            offset=params["offset"]
            if offset==0:
                return {"_embedded":{"items":[yf(i) for i in range(100)],"total":101}}
            return {"_embedded":{"items":[yf(100)],"total":101}}
        with patch("backend.cloud_drives._yandex_api",side_effect=api):
            items=cloud_drives._yandex_files(None,{},"/",False)
        self.assertEqual(len(items),101)
        self.assertTrue(all(not x["web_view_url"] for x in items))
        self.assertNotIn("sig=test-only",repr(items))

    def test_yandex_incomplete_page_detected(self):
        with patch("backend.cloud_drives._yandex_api",return_value={
            "_embedded":{"items":[],"total":100}
        }):
            with self.assertRaises(business.DomainError) as context:
                cloud_drives._yandex_files(None,{},"/",False)
        self.assertEqual(context.exception.status,502)

    def test_yandex_request_budget(self):
        def api(_con,_connection,_path,params):
            return {"_embedded":{"items":[yf(params["offset"])],"total":1000}}
        with patch("backend.cloud_drives.MAX_SCAN_REQUESTS",4),patch(
            "backend.cloud_drives._yandex_api",side_effect=api
        ) as remote:
            with self.assertRaises(business.DomainError) as context:
                cloud_drives._yandex_files(None,{},"/",False)
        self.assertEqual(context.exception.status,503)
        self.assertEqual(remote.call_count,4)

    def test_yandex_file_cap_detected(self):
        with patch("backend.cloud_drives._yandex_api",return_value={
            "_embedded":{"items":[yf(i) for i in range(1501)],"total":1501}
        }):
            with self.assertRaises(business.DomainError) as context:
                cloud_drives._yandex_files(None,{},"/",False)
        self.assertEqual(context.exception.status,422)


class SignedLinkPrivacyTests(unittest.TestCase):
    def _database(self):
        con=sqlite3.connect(":memory:")
        con.row_factory=sqlite3.Row
        con.executescript("""
        CREATE TABLE cloud_connections(id TEXT PRIMARY KEY,provider TEXT,account_label TEXT);
        CREATE TABLE cloud_folder_bindings(
            id TEXT PRIMARY KEY,workspace_id TEXT,connection_id TEXT,status TEXT,
            sync_requested INTEGER,next_sync_at INTEGER,created_at INTEGER,
            quote_id TEXT,project_id TEXT,folder_name TEXT);
        CREATE TABLE cloud_files(
            id TEXT PRIMARY KEY,connection_id TEXT,binding_id TEXT,name TEXT,
            web_view_url TEXT,mime TEXT,size INTEGER);
        CREATE TABLE document_processing_jobs(
            id TEXT PRIMARY KEY,workspace_id TEXT,cloud_file_id TEXT,
            status TEXT,progress TEXT,error TEXT,attempts INTEGER,
            created_at INTEGER,updated_at INTEGER,extraction TEXT,proposal TEXT);
        INSERT INTO cloud_connections VALUES('yandex','yandex_disk','Yandex');
        INSERT INTO cloud_connections VALUES('google','google_drive','Google');
        INSERT INTO cloud_folder_bindings(
            id,workspace_id,connection_id,status,sync_requested,next_sync_at,created_at,folder_name)
        VALUES('folder-y','workspace-1','yandex','disabled',0,9999999999,1,'Bills'),
              ('folder-g','workspace-1','google','disabled',0,9999999999,2,'Bills');
        INSERT INTO cloud_files VALUES('f-y','yandex','folder-y','bill.pdf',
            'https://files.example.invalid/download?sig=test-only','application/pdf',200);
        INSERT INTO cloud_files VALUES('f-g','google','folder-g','bill.pdf',
            'https://drive.google.com/file/d/id/view','application/pdf',200);
        INSERT INTO document_processing_jobs
            (id,workspace_id,cloud_file_id,status,progress,error,attempts,created_at,updated_at,extraction,proposal)
        VALUES('j-y','workspace-1','f-y','needs_review','Ready','',1,1,1,'{}','{}'),
              ('j-g','workspace-1','f-g','needs_review','Ready','',1,1,1,'{}','{}');
        """)
        con.commit()
        return con

    def test_jobs_list_and_details_hide_legacy_signed_download_links(self):
        con=self._database()
        service=Mock(con=con,wid="workspace-1")
        try:
            with patch("backend.cloud_drives._premium_access"):
                _,listing=cloud_drives.route(service,"GET",["jobs"],{}, {})
                self.assertEqual(
                    {x["id"]:x["web_view_url"] for x in listing["jobs"]},
                    {"j-y":"","j-g":"https://drive.google.com/file/d/id/view"}
                )
                _,detail=cloud_drives.route(service,"GET",["jobs","j-y"],{}, {})
                self.assertEqual(detail["job"]["web_view_url"],"")
        finally:
            con.close()

    def test_cron_scrubs_old_links_without_erasing_google_view_url(self):
        con=self._database()
        try:
            with patch("backend.cloud_drives._process_jobs",return_value={}):
                result=cloud_drives.run_cloud_batch(con,limit=1)
            self.assertEqual(result["bindings_checked"],0)
            links=dict(con.execute("SELECT id,web_view_url FROM cloud_files"))
            self.assertEqual(links["f-y"],"")
            self.assertEqual(links["f-g"],"https://drive.google.com/file/d/id/view")
        finally:
            con.close()


if __name__=="__main__":
    unittest.main()
