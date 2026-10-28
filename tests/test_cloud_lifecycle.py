"""Exercise cloud removal, content changes and retries against the real API/SQL."""
import json
import unittest
import uuid
from unittest.mock import patch

from backend import business, cloud_drives
from tests import test_business as business_tests


class CloudLifecycleTests(unittest.TestCase):
    setUpClass = classmethod(business_tests.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(business_tests.BusinessFlows.tearDownClass.__func__)
    call = business_tests.BusinessFlows.call
    account = business_tests.BusinessFlows.account

    def setUp(self):
        business_tests.BusinessFlows.setUp(self)
        with self.mod.db() as con:
            con.execute("DELETE FROM document_processing_jobs")
        self.token, self.user_id = self.account("cloud-" + uuid.uuid4().hex[:12])
        code, result = self.call("/quotes", "POST", {
            "title": "Облачная смета", "client": "Клиент", "items": [
                {"name": "Исходная работа", "quantity": "1", "unit_price": 10000}
            ],
        }, self.token)
        self.assertEqual(code, 201, result)
        self.quote = result["quote"]
        self.connection, self.binding, self.file, self.job = [str(uuid.uuid4()) for _ in range(4)]
        now = self.mod.now()
        with self.mod.db() as con:
            self.wid = con.execute(
                "SELECT workspace_id FROM workspace_members WHERE user_id=?", (self.user_id,)
            ).fetchone()[0]
            con.execute(
                "UPDATE workspaces SET plan='pro_plus_month',subscription_status='active',entitlement_until=? WHERE id=?",
                (now + 86400, self.wid),
            )
            con.execute(
                "INSERT INTO cloud_connections(id,workspace_id,user_id,provider,access_token_enc,refresh_token_enc,created_at,updated_at) "
                "VALUES(?,?,?,'google_drive','private-access','private-refresh',?,?)",
                (self.connection, self.wid, self.user_id, now, now),
            )
            con.execute(
                "INSERT INTO cloud_folder_bindings(id,workspace_id,connection_id,folder_id,quote_id,next_sync_at,created_by,created_at,updated_at) "
                "VALUES(?,?,?,'root',?,?,?,?,?)",
                (self.binding, self.wid, self.connection, self.quote["id"], now, self.user_id, now, now),
            )
            con.execute(
                "INSERT INTO cloud_files(id,workspace_id,binding_id,connection_id,provider_file_id,name,mime,size,source_fingerprint,processing_status,first_seen_at,updated_at) "
                "VALUES(?,?,?,?,'provider-file','bill.pdf','application/pdf',200,'version-a','needs_review',?,?)",
                (self.file, self.wid, self.binding, self.connection, now, now),
            )
            proposal = {"needs_confirmation": True, "items": [
                {"name": "Материал из счёта", "quantity": "2", "unit_price_kopecks": 15000}
            ]}
            con.execute(
                "INSERT INTO document_processing_jobs(id,workspace_id,cloud_file_id,source_fingerprint,status,proposal,next_attempt_at,created_at,updated_at) "
                "VALUES(?,?,?,'version-a','needs_review',?,?,?,?)",
                (self.job, self.wid, self.file, json.dumps(proposal), now, now, now),
            )

    def import_job(self):
        return self.call("/premium/cloud/jobs/" + self.job, "POST", {}, self.token)

    def unchanged_quote(self):
        code, result = self.call("/quotes/" + self.quote["id"], token=self.token)
        self.assertEqual(code, 200, result)
        self.assertEqual(result["quote"]["amount_kopecks"], 10000)
        self.assertEqual(len(result["quote"]["items"]), 1)

    def test_disconnect_reads_delete_json_and_erases_credentials(self):
        code, result = self.call("/premium/cloud/connections", "DELETE", {
            "connection_id": self.connection,
        }, self.token)
        self.assertEqual(code, 200, result)
        with self.mod.db() as con:
            row = con.execute("SELECT * FROM cloud_connections WHERE id=?", (self.connection,)).fetchone()
            self.assertEqual((row["status"], row["access_token_enc"], row["refresh_token_enc"]), ("disabled", "", ""))
            self.assertEqual(con.execute("SELECT status FROM cloud_folder_bindings WHERE id=?", (self.binding,)).fetchone()[0], "disabled")
        self.assertEqual(self.import_job()[0], 409)
        self.unchanged_quote()

    def test_only_current_connected_document_can_be_imported(self):
        for sql in (
            "UPDATE cloud_files SET source_fingerprint='version-b' WHERE id=?",
            "UPDATE cloud_files SET trashed=1 WHERE id=?",
            "UPDATE cloud_folder_bindings SET status='disabled' WHERE id=?",
            "UPDATE cloud_connections SET status='disabled' WHERE id=?",
        ):
            with self.subTest(sql=sql):
                with self.mod.db() as con:
                    con.execute("UPDATE cloud_files SET source_fingerprint='version-a',trashed=0 WHERE id=?", (self.file,))
                    con.execute("UPDATE cloud_folder_bindings SET status='active' WHERE id=?", (self.binding,))
                    con.execute("UPDATE cloud_connections SET status='active' WHERE id=?", (self.connection,))
                    ident = self.file if "cloud_files" in sql else self.binding if "cloud_folder_bindings" in sql else self.connection
                    con.execute(sql, (ident,))
                self.assertEqual(self.import_job()[0], 409)
                self.unchanged_quote()

    def test_confirmed_document_is_imported_exactly_once(self):
        code, result = self.import_job()
        self.assertEqual(code, 200, result)
        self.assertEqual(result["imported_items"], 1)
        self.assertEqual(self.import_job()[0], 409)
        current = self.call("/quotes/" + self.quote["id"], token=self.token)[1]["quote"]
        self.assertEqual(len(current["items"]), 2)
        self.assertEqual(current["amount_kopecks"], 40000)

    def scan(self, con, files):
        binding = dict(con.execute("SELECT * FROM cloud_folder_bindings WHERE id=?", (self.binding,)).fetchone())
        with patch("backend.cloud_drives._google_files", return_value=files):
            return cloud_drives._sync_binding(con, binding)

    def entry(self, fingerprint="version-a"):
        return {"provider_file_id": "provider-file", "parent_folder_id": "root",
                "name": "bill.pdf", "mime": "application/pdf", "size": 200,
                "modified_at": "2026-10-28T10:00:00Z", "fingerprint": fingerprint,
                "web_view_url": ""}

    def test_deleted_document_review_is_cancelled_and_restoration_can_run_again(self):
        with self.mod.db() as con:
            self.assertEqual(self.scan(con, []), 0)
            self.assertEqual(con.execute("SELECT trashed FROM cloud_files WHERE id=?", (self.file,)).fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT status FROM document_processing_jobs WHERE id=?", (self.job,)).fetchone()[0], "cancelled")
            self.scan(con, [self.entry()])
            row = con.execute("SELECT status,attempts FROM document_processing_jobs WHERE id=?", (self.job,)).fetchone()
            self.assertEqual((row["status"], row["attempts"]), ("queued", 0))
            self.assertEqual(con.execute("SELECT count(*) FROM document_processing_jobs WHERE cloud_file_id=?", (self.file,)).fetchone()[0], 1)

    def test_changed_document_cancels_only_unconfirmed_old_version(self):
        with self.mod.db() as con:
            self.scan(con, [self.entry("version-b")])
            rows = con.execute("SELECT source_fingerprint,status FROM document_processing_jobs WHERE cloud_file_id=?", (self.file,)).fetchall()
            self.assertEqual({r[0]: r[1] for r in rows}, {"version-a": "cancelled", "version-b": "queued"})
        self.assertEqual(self.import_job()[0], 409)
        self.unchanged_quote()

    def test_restored_imported_bytes_do_not_duplicate_the_import(self):
        self.assertEqual(self.import_job()[0], 200)
        with self.mod.db() as con:
            self.scan(con, [])
            self.scan(con, [self.entry()])
            self.assertEqual(con.execute("SELECT status FROM document_processing_jobs WHERE id=?", (self.job,)).fetchone()[0], "completed")
            self.assertEqual(con.execute("SELECT processing_status FROM cloud_files WHERE id=?", (self.file,)).fetchone()[0], "processed")
        self.assertEqual(self.import_job()[0], 409)

    def test_failed_scan_preserves_last_known_contents(self):
        with self.mod.db() as con:
            binding = dict(con.execute("SELECT * FROM cloud_folder_bindings WHERE id=?", (self.binding,)).fetchone())
            with patch("backend.cloud_drives._google_files", side_effect=business.DomainError(503, "Лимит обхода")):
                with self.assertRaises(business.DomainError):
                    cloud_drives._sync_binding(con, binding)
            self.assertEqual(con.execute("SELECT trashed FROM cloud_files WHERE id=?", (self.file,)).fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT status FROM document_processing_jobs WHERE id=?", (self.job,)).fetchone()[0], "needs_review")

    def test_document_failure_stops_after_three_attempts(self):
        with self.mod.db() as con, patch("backend.cloud_drives._download", side_effect=business.DomainError(503, "Недоступен")) as download:
            con.execute("UPDATE document_processing_jobs SET status='queued',next_attempt_at=0 WHERE id=?", (self.job,))
            for attempt in (1, 2, 3):
                con.execute("UPDATE document_processing_jobs SET next_attempt_at=0 WHERE id=?", (self.job,))
                result = cloud_drives._process_jobs(con)
                self.assertEqual(result["failed"], 1)
                row = con.execute("SELECT status,attempts FROM document_processing_jobs WHERE id=?", (self.job,)).fetchone()
                self.assertEqual(row["attempts"], attempt)
                self.assertEqual(row["status"], "failed" if attempt == 3 else "retry")
            self.assertEqual(cloud_drives._process_jobs(con)["failed"], 0)
            self.assertEqual(download.call_count, 3)

    def test_crashed_final_attempt_is_terminal_without_another_provider_call(self):
        with self.mod.db() as con, patch("backend.cloud_drives._download") as download:
            con.execute("UPDATE document_processing_jobs SET status='running',attempts=3,lease_until=0 WHERE id=?", (self.job,))
            self.assertEqual(cloud_drives._process_jobs(con)["failed"], 1)
            row = con.execute("SELECT status,attempts FROM document_processing_jobs WHERE id=?", (self.job,)).fetchone()
            self.assertEqual((row["status"], row["attempts"]), ("failed", 3))
            download.assert_not_called()

    def test_expired_subscription_can_still_disconnect_cloud(self):
        with self.mod.db() as con:
            con.execute("UPDATE workspaces SET entitlement_until=1 WHERE id=?", (self.wid,))
        code, result = self.call("/premium/cloud/connections", "DELETE", {"connection_id": self.connection}, self.token)
        self.assertEqual(code, 200, result)

    def test_expired_subscription_or_removed_manager_cannot_read_cloud(self):
        with self.mod.db() as con:
            for reason in ("expired", "demoted", "blocked"):
                with self.subTest(reason=reason), patch("backend.cloud_drives._google_files") as scan, patch("backend.cloud_drives._download") as download:
                    con.execute("UPDATE workspaces SET entitlement_until=? WHERE id=?", (1 if reason == "expired" else self.mod.now() + 3600, self.wid))
                    con.execute("UPDATE workspace_members SET role=? WHERE workspace_id=? AND user_id=?", ("viewer" if reason == "demoted" else "owner", self.wid, self.user_id))
                    con.execute("UPDATE users SET blocked=? WHERE id=?", (int(reason == "blocked"), self.user_id))
                    with self.assertRaises(business.DomainError) as error:
                        self.scan(con, [])
                    self.assertEqual(error.exception.status, 402 if reason == "expired" else 403)
                    con.execute("UPDATE document_processing_jobs SET status='queued',attempts=0,next_attempt_at=0 WHERE id=?", (self.job,))
                    self.assertEqual(cloud_drives._process_jobs(con)["failed"], 1)
                    scan.assert_not_called()
                    download.assert_not_called()

    def test_failed_current_document_can_be_retried_without_creating_another_job(self):
        with self.mod.db() as con:
            con.execute("UPDATE document_processing_jobs SET status='failed',attempts=3,error='Временная ошибка' WHERE id=?", (self.job,))
        path = "/premium/cloud/jobs/" + self.job + "/retry"
        code, result = self.call(path, "POST", {}, self.token)
        self.assertEqual(code, 202, result)
        self.assertEqual(self.call(path, "POST", {}, self.token)[0], 409)
        with self.mod.db() as con:
            row = con.execute("SELECT status,attempts,error FROM document_processing_jobs WHERE id=?", (self.job,)).fetchone()
            self.assertEqual((row["status"], row["attempts"], row["error"]), ("queued", 0, ""))
            self.assertEqual(con.execute("SELECT count(*) FROM document_processing_jobs WHERE cloud_file_id=?", (self.file,)).fetchone()[0], 1)
        self.unchanged_quote()

    def test_obsolete_or_completed_document_cannot_be_retried(self):
        path = "/premium/cloud/jobs/" + self.job + "/retry"
        with self.mod.db() as con:
            con.execute("UPDATE document_processing_jobs SET status='failed' WHERE id=?", (self.job,))
            con.execute("UPDATE cloud_files SET source_fingerprint='new-content' WHERE id=?", (self.file,))
        self.assertEqual(self.call(path, "POST", {}, self.token)[0], 409)
        with self.mod.db() as con:
            con.execute("UPDATE cloud_files SET source_fingerprint='version-a' WHERE id=?", (self.file,))
            con.execute("UPDATE document_processing_jobs SET status='completed' WHERE id=?", (self.job,))
        self.assertEqual(self.call(path, "POST", {}, self.token)[0], 409)

    def test_token_refresh_cannot_restore_a_disconnected_account(self):
        with self.mod.db() as con:
            connection = dict(con.execute("SELECT * FROM cloud_connections WHERE id=?", (self.connection,)).fetchone())
            con.execute("UPDATE cloud_connections SET status='disabled',access_token_enc='',refresh_token_enc='' WHERE id=?", (self.connection,))
            with patch("backend.cloud_drives._encrypt", return_value="encrypted-new-access"):
                with self.assertRaises(business.DomainError) as error:
                    cloud_drives._save_access(con, connection, "new-access")
            self.assertEqual(error.exception.status, 409)
            row = con.execute("SELECT status,access_token_enc,refresh_token_enc FROM cloud_connections WHERE id=?", (self.connection,)).fetchone()
            self.assertEqual(tuple(row), ("disabled", "", ""))

    def test_transient_token_refresh_outage_does_not_require_reauthorization(self):
        with self.mod.db() as con:
            connection = dict(con.execute("SELECT * FROM cloud_connections WHERE id=?", (self.connection,)).fetchone())
            for status in (503, 409):
                with self.subTest(status=status), patch("backend.cloud_drives._decrypt", return_value="test-refresh"), patch(
                    "backend.cloud_drives._credentials", return_value=("fixture", "fixture", "https://example.test/callback")
                ), patch("backend.cloud_drives._http", side_effect=business.DomainError(status, "Provider unavailable")):
                    with self.assertRaises(business.DomainError):
                        cloud_drives._access_token(con, connection)
                    row = con.execute("SELECT status,refresh_token_enc FROM cloud_connections WHERE id=?", (self.connection,)).fetchone()
                    self.assertEqual(row["status"], "active" if status == 503 else "reauth_required")
                    self.assertEqual(row["refresh_token_enc"], "private-refresh")
