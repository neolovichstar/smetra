"""Cloud worker safety: OAuth headers and document processing leases."""
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch
from urllib.request import Request

from backend import cloud_drives, business


def job_row():
    return {
        "id": "job-1", "workspace_id": "space-a", "cloud_file_id": "file-1",
        "provider_file_id": "provider-file-1", "name": "Счёт.pdf",
        "mime": "application/pdf", "provider_mime": "application/pdf",
        "size": 800, "connection_id": "conn-1", "quote_id": None,
        "project_id": None, "provider": "google_drive",
        "access_token_enc": "encrypted", "refresh_token_enc": "encrypted",
        "token_expires_at": 99999999, "status": "running",
        "connection_status": "active",
    }


class FakeCursor:
    def __init__(self, row=None, *, rowcount=1):
        self.row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self.row


class TrackingConnection:
    def __init__(self, update_rowcount):
        self.calls = []
        self.update_rowcount = update_rowcount

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql.startswith("SELECT j.*"):
            return FakeCursor(job_row())
        if sql.startswith("SELECT * FROM cloud_connections"):
            return FakeCursor({
                "id": "conn-1", "workspace_id": "space-a",
                "provider": "google_drive", "status": "active"
            })
        if sql.startswith("UPDATE document_processing_jobs"):
            return FakeCursor(rowcount=self.update_rowcount)
        return FakeCursor()


class ProviderApiRedirectTests(unittest.TestCase):
    def test_api_rejects_cross_origin_oauth_redirects(self):
        request = Request(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": "Bearer SENSITIVE_TOKEN"},
        )
        handler = cloud_drives._SameOriginApiRedirect()
        self.assertIsNone(handler.redirect_request(
            request, None, 302, "Found", {},
            "https://files.googleusercontent.com/collect"
        ))
        self.assertIsNone(handler.redirect_request(
            request, None, 302, "Found", {},
            "http://www.googleapis.com/collect"
        ))
        self.assertIsNone(handler.redirect_request(
            request, None, 302, "Found", {},
            "https://www.googleapis.com:444/collect"
        ))

    def test_api_allows_same_https_origin_redirect(self):
        request = Request(
            "https://oauth2.googleapis.com/token",
            headers={"Authorization": "Bearer SENSITIVE_TOKEN"},
        )
        result = cloud_drives._SameOriginApiRedirect().redirect_request(
            request, None, 302, "Found", {},
            "https://oauth2.googleapis.com/another-endpoint"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.get_header("Authorization"), "Bearer SENSITIVE_TOKEN")


class RedirectSafetyTests(unittest.TestCase):
    def test_google_redirect_to_signed_download_host_does_not_forward_bearer(self):
        url = "https://www.googleapis.com/drive/v3/files/file-1?alt=media"
        req = Request(url, headers={
            "Authorization": "Bearer SECRET_ACCESS_TOKEN",
            "Cookie": "session=private",
            "Proxy-Authorization": "Basic PRIVATE",
            "User-Agent": "SmetraCloudSync/1.0",
        })
        with patch("backend.cloud_drives._safe_cloud_href", return_value=True):
            redirected = cloud_drives._SafeDownloadRedirect().redirect_request(
                req, None, 302, "Found", {},
                "https://files.googleusercontent.com/download/file-1"
            )
        self.assertIsNotNone(redirected)
        self.assertNotIn("Authorization", redirected.headers)
        self.assertNotIn("Cookie", redirected.headers)
        self.assertNotIn("Proxy-authorization", redirected.headers)
        self.assertEqual(redirected.get_header("User-agent"), "SmetraCloudSync/1.0")

    def test_same_host_redirect_can_preserve_authentication(self):
        req = Request("https://www.googleapis.com/drive/v3/files/file-1",
                      headers={"Authorization": "Bearer ACCESS_TOKEN"})
        with patch("backend.cloud_drives._safe_cloud_href", return_value=True):
            redirected = cloud_drives._SafeDownloadRedirect().redirect_request(
                req, None, 302, "Found", {}, "https://www.googleapis.com/download/file-1"
            )
        self.assertEqual(redirected.get_header("Authorization"), "Bearer ACCESS_TOKEN")

    def test_unsafe_redirect_still_rejected(self):
        req = Request("https://www.googleapis.com/file", headers={"Authorization": "Bearer SECRET"})
        redirected = cloud_drives._SafeDownloadRedirect().redirect_request(
            req, None, 302, "Found", {}, "http://127.0.0.1/internal"
        )
        self.assertIsNone(redirected)

    def test_bounded_redirect_count(self):
        req = Request("https://www.googleapis.com/file", headers={"Authorization": "Bearer SECRET"})
        handler = cloud_drives._SafeDownloadRedirect()
        with patch("backend.cloud_drives._safe_cloud_href", return_value=True):
            for _ in range(4):
                self.assertIsNotNone(handler.redirect_request(
                    req, None, 302, "Found", {}, "https://files.googleusercontent.com/file"
                ))
            self.assertIsNone(handler.redirect_request(
                req, None, 302, "Found", {}, "https://files.googleusercontent.com/file"
            ))


class DocumentLeaseTests(unittest.TestCase):
    def exercise_job(self, rowcount, failure=False):
        con = TrackingConnection(rowcount)
        job = {"id": "job-1", "lease_token": "old-lease", "attempts": 1}
        proposal = {"needs_confirmation": True, "items": [{"name": "Сметная строка"}]}
        with (
            patch("backend.business.transaction", return_value=nullcontext()),
            patch("backend.cloud_drives._download", side_effect=business.DomainError(502, "provider error") if failure else None,
                  return_value=b"%PDF"),
            patch("backend.cloud_drives._model_extract", return_value=proposal),
            patch("backend.push.enqueue") as enqueue,
        ):
            state = cloud_drives._document_job(con, job)
        return state, con.calls, enqueue

    def test_expired_lease_cannot_reopen_review_or_duplicate_notifications(self):
        state, calls, enqueue = self.exercise_job(rowcount=0)
        self.assertEqual(state, "stale")
        self.assertTrue(any("lease_token=? AND status='running'" in sql for sql, _ in calls))
        self.assertFalse(any("UPDATE cloud_files" in sql for sql, _ in calls))
        self.assertFalse(any("INSERT INTO notifications" in sql for sql, _ in calls))
        enqueue.assert_not_called()

    def test_expired_lease_cannot_overwrite_success_with_retry_or_failure(self):
        state, calls, enqueue = self.exercise_job(rowcount=0, failure=True)
        self.assertEqual(state, "stale")
        self.assertFalse(any("UPDATE cloud_files" in sql for sql, _ in calls))
        self.assertFalse(any("INSERT INTO notifications" in sql for sql, _ in calls))
        enqueue.assert_not_called()

    def test_valid_lease_can_publish_one_review(self):
        state, calls, enqueue = self.exercise_job(rowcount=1)
        self.assertEqual(state, "needs_review")
        self.assertEqual(sum("UPDATE cloud_files" in sql for sql, _ in calls), 1)
        self.assertEqual(sum("INSERT INTO notifications" in sql for sql, _ in calls), 1)
        enqueue.assert_called_once()

    def test_reclaimed_jobs_are_not_counted_as_processed(self):
        con = Mock()
        queued = dict(job_row(), attempts=1, lease_token="")
        con.execute.return_value.fetchall.return_value = [queued]
        with (
            patch("backend.business.transaction", return_value=nullcontext()),
            patch("backend.cloud_drives._document_job", return_value="stale"),
        ):
            counts = cloud_drives._process_jobs(con, limit=1)
        self.assertEqual(counts, {"processed": 0, "review": 0, "failed": 0, "stale_ignored": 1})

    def test_valid_lease_marks_failed_document(self):
        state, calls, enqueue = self.exercise_job(rowcount=1, failure=True)
        self.assertEqual(state, "retry")
        self.assertEqual(sum("UPDATE cloud_files" in sql for sql, _ in calls), 1)
        enqueue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
