"""Background document preparation is bounded, free and fenced against races."""

import base64
import io
import hashlib
import os
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_business
from test_assistant_jobs import SECRET, worker_token
from backend.business import Service


class FileProcessingTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def setUp(self):
        test_business.BusinessFlows.setUp(self)
        env = patch.dict(
            os.environ, ASSISTANT_WORKER_SECRET=SECRET, OPENROUTER_API_KEY="test-only"
        )
        env.start()
        self.addCleanup(env.stop)
        with self.mod.db() as con:
            con.execute("DELETE FROM assistant_jobs")

    def upload(self, owner, raw=None, name="large.txt"):
        raw = raw if raw is not None else b"Paint walls. " + b"A" * 110_000
        code, result = self.call(
            "/files",
            "POST",
            {
                "assistant_upload": True,
                "name": name,
                "content": base64.b64encode(raw).decode(),
            },
            owner,
        )
        self.assertEqual(code, 201, result)
        return result["file"]

    def status(self, owner, file):
        code, result = self.call("/files/" + file["id"] + "/metadata", token=owner)
        self.assertEqual(code, 200, result)
        return result["processing"]

    def work(self, result=None, side_effect=None):
        with patch("backend.assistant.query_model") as model:
            if result is None and side_effect is None:
                code, body = self.call("/cron/assistant", token=worker_token())
            else:
                with patch(
                    "backend.file_processing.isolated_extract",
                    return_value=result,
                    side_effect=side_effect,
                ):
                    code, body = self.call("/cron/assistant", token=worker_token())
        self.assertEqual(code, 200, body)
        model.assert_not_called()

    def service(self, owner):
        con = self.enterContext(self.mod.db())
        user = con.execute(
            "SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=?",
            (hashlib.sha256(owner.encode()).hexdigest(),),
        ).fetchone()
        wid = con.execute(
            "SELECT workspace_id FROM workspace_members WHERE user_id=?", (user["id"],)
        ).fetchone()[0]
        service = Service(SimpleNamespace(), con, "http://localhost")
        service.user, service.wid = user, wid
        return service

    def test_large_document_ready_survives_navigation_and_never_spends_quota(self):
        from backend.assistant_files import read_file, search_content

        owner, _ = self.account("file-ready")
        file = self.upload(owner, b"Paint walls. " + b"A" * 2_100_000)
        info = self.status(owner, file)
        self.assertEqual(info["state"], "queued")
        self.assertNotIn("session_hash", str(info))
        self.work()
        info = self.status(owner, file)
        self.assertEqual(info["state"], "ready")
        self.assertTrue(info["truncated"])
        self.assertEqual(self.call("/assistant", token=owner)[1]["quota"]["used"], 0)
        service = self.service(owner)
        self.assertIn(
            "Paint walls", read_file(service, file["id"])["excerpts"][0]["text"]
        )
        self.assertEqual(
            search_content(service, "paint")["items"][0]["file_id"], file["id"]
        )
        with self.mod.db() as con:
            self.assertEqual(
                con.execute("SELECT count(*) FROM assistant_messages").fetchone()[0], 0
            )

    def test_pending_context_rejects_chat_without_reserving_message(self):
        owner, _ = self.account("file-not-ready")
        file = self.upload(owner)
        for path in ("/assistant/chat", "/assistant/stream", "/assistant/jobs"):
            code, result = self.call(
                path,
                "POST",
                {"text": "Read it", "context": {"entity": "files", "id": file["id"]}},
                owner,
                key="ask-file",
            )
            self.assertEqual(code, 409, result)
        self.assertEqual(self.call("/assistant", token=owner)[1]["quota"]["used"], 0)

    def test_cancel_then_retry_and_private_job_access(self):
        owner, _ = self.account("file-cancel")
        outsider, _ = self.account("file-outsider")
        file = self.upload(owner)
        job = self.status(owner, file)["job_id"]
        self.assertEqual(
            self.call("/files/" + file["id"] + "/processing", token=outsider)[0], 404
        )
        self.assertEqual(self.call("/assistant/jobs/" + job, token=outsider)[0], 404)
        endpoint = "/files/" + file["id"] + "/processing"
        self.assertEqual(
            self.call(endpoint, "DELETE", token=owner)[1]["processing"]["state"],
            "cancelled",
        )
        self.work()
        for _ in range(2):
            self.assertEqual(
                self.call(endpoint, "POST", {}, owner, key="prepare-retry")[0], 202
            )
        newjob = self.status(owner, file)["job_id"]
        self.assertNotEqual(job, newjob)
        self.work()
        self.assertEqual(self.status(owner, file)["state"], "ready")

    def test_cancel_during_extraction_does_not_save_chunks(self):
        owner, _ = self.account("file-inflight-cancel")
        file = self.upload(owner)

        def extract(*args):
            self.call("/files/" + file["id"] + "/processing", "DELETE", token=owner)
            return {"pages": [[1, "Do not save"]], "truncated": False}

        self.work(side_effect=extract)
        self.assertEqual(self.status(owner, file)["state"], "cancelled")
        with self.mod.db() as con:
            self.assertEqual(
                con.execute(
                    "SELECT count(*) FROM file_text_chunks WHERE file_id=?",
                    (file["id"],),
                ).fetchone()[0],
                0,
            )

    def test_logout_during_extraction_does_not_commit(self):
        owner, uid = self.account("file-logout")
        file = self.upload(owner)

        def extract(*args):
            with self.mod.db() as con:
                con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            return {"pages": [[1, "Not saved"]], "truncated": False}

        self.work(side_effect=extract)
        with self.mod.db() as con:
            self.assertEqual(
                con.execute(
                    "SELECT index_status FROM files WHERE id=?", (file["id"],)
                ).fetchone()[0],
                "failed",
            )
            self.assertEqual(
                con.execute(
                    "SELECT count(*) FROM file_text_chunks WHERE file_id=?",
                    (file["id"],),
                ).fetchone()[0],
                0,
            )

    def test_changed_source_cannot_overwrite_new_index(self):
        owner, _ = self.account("file-edited")
        file = self.upload(owner, name="large.md")

        def extract(*args):
            result = self.call(
                "/files/" + file["id"],
                "PATCH",
                {
                    "sha256": file["sha256"],
                    "content": base64.b64encode(b"New version").decode(),
                },
                owner,
            )
            self.assertEqual(result[0], 200, result)
            return {"pages": [[1, "Old version"]], "truncated": False}

        self.work(side_effect=extract)
        self.assertEqual(self.status(owner, file)["state"], "ready")
        with self.mod.db() as con:
            self.assertEqual(
                con.execute(
                    "SELECT text FROM file_text_chunks WHERE file_id=?", (file["id"],)
                ).fetchone()[0],
                "New version",
            )

    def test_timeout_is_terminal_and_retry_is_explicit(self):
        owner, _ = self.account("file-timeout")
        file = self.upload(owner)
        self.work(side_effect=subprocess.TimeoutExpired("extractor", 25))
        self.assertEqual(self.status(owner, file)["state"], "failed")
        self.assertEqual(self.call("/assistant", token=owner)[1]["quota"]["used"], 0)
        self.assertEqual(
            self.call(
                "/files/" + file["id"] + "/processing",
                "POST",
                {},
                owner,
                key="after-timeout",
            )[0],
            202,
        )
        self.work()
        self.assertEqual(self.status(owner, file)["state"], "ready")

    def test_no_text_pdf_reports_ocr_requirement_without_calling_model(self):
        owner, _ = self.account("file-scan")
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        stream = io.BytesIO()
        writer.write(stream)
        file = self.upload(owner, stream.getvalue(), "scan.pdf")
        self.assertEqual(self.status(owner, file)["state"], "queued")
        self.work()
        self.assertEqual(self.status(owner, file)["state"], "needs_ocr")

    def test_pdf_real_subprocess_produces_utf8_text(self):
        owner, _ = self.account("file-pdf")
        raw = (
            Path(__file__).parents[1]
            / "apps/mobile/app/src/androidTest/assets/brief.pdf"
        ).read_bytes()
        file = self.upload(owner, raw, "brief.pdf")
        self.work()
        self.assertEqual(self.status(owner, file)["state"], "ready")

    def test_invalid_extractor_output_fails_without_partial_result(self):
        owner, _ = self.account("file-bad-output")
        file = self.upload(owner)
        self.work(result={"pages": [[0, "invalid"]], "truncated": False})
        self.assertEqual(self.status(owner, file)["state"], "failed")

    def test_queue_capacity_preserves_upload_and_does_not_block_unrelated_chat(self):
        owner, _ = self.account("file-capacity")
        for _ in range(10):
            self.upload(owner)
        file = self.upload(owner)
        self.assertEqual(self.status(owner, file)["state"], "deferred")
        code, result = self.call(
            "/assistant/jobs",
            "POST",
            {"text": "Unrelated question"},
            owner,
            key="independent-chat",
        )
        self.assertEqual(code, 202, result)
        self.assertEqual(self.call("/assistant", token=owner)[1]["quota"]["used"], 1)

    def test_lost_worker_lease_cannot_save_text(self):
        from backend.assistant_jobs import claim

        owner, _ = self.account("file-lease")
        file = self.upload(owner)
        job = self.status(owner, file)["job_id"]

        def extract(*args):
            with self.mod.db() as con:
                con.execute(
                    "UPDATE assistant_jobs SET lease_until=0 WHERE id=?", (job,)
                )
            with self.mod.db() as con:
                self.assertEqual(claim(con)["attempts"], 2)
            return {"pages": [[1, "Old attempt"]], "truncated": False}

        self.work(side_effect=extract)
        with self.mod.db() as con:
            self.assertEqual(
                con.execute(
                    "SELECT count(*) FROM file_text_chunks WHERE file_id=?",
                    (file["id"],),
                ).fetchone()[0],
                0,
            )
            con.execute("UPDATE assistant_jobs SET lease_until=0 WHERE id=?", (job,))
        self.work()
        self.assertEqual(self.status(owner, file)["state"], "ready")

    def test_deleted_file_removes_queued_job(self):
        owner, _ = self.account("file-delete")
        file = self.upload(owner)
        job = self.status(owner, file)["job_id"]
        self.assertEqual(
            self.call("/files/" + file["id"], "DELETE", token=owner)[0], 200
        )
        self.work()
        self.assertEqual(self.call("/assistant/jobs/" + job, token=owner)[0], 404)

    def test_revoked_membership_during_extraction_does_not_save(self):
        owner, uid = self.account("file-role")
        file = self.upload(owner)

        def extract(*args):
            with self.mod.db() as con:
                con.execute(
                    "UPDATE workspace_members SET role='viewer' WHERE user_id=?", (uid,)
                )
            return {"pages": [[1, "Not saved"]], "truncated": False}

        self.work(side_effect=extract)
        with self.mod.db() as con:
            self.assertEqual(
                con.execute(
                    "SELECT index_status FROM files WHERE id=?", (file["id"],)
                ).fetchone()[0],
                "failed",
            )
            self.assertEqual(
                con.execute(
                    "SELECT count(*) FROM file_text_chunks WHERE file_id=?",
                    (file["id"],),
                ).fetchone()[0],
                0,
            )


class ExtractorBoundsTests(unittest.TestCase):
    def test_vercel_transport_cap_includes_base64_overhead(self):
        from backend.attachments import maximum_upload

        with patch.dict(os.environ,VERCEL='1',MAX_UPLOAD_BYTES='5000000'):
            self.assertEqual(maximum_upload(),3_000_000)
        with patch.dict(os.environ,VERCEL='0',MAX_UPLOAD_BYTES='5000000'):
            self.assertEqual(maximum_upload(),5_000_000)

    def test_text_and_pdf_bounds(self):
        from backend.file_extractor import extract

        self.assertEqual(extract("Сметра".encode(), "text/plain")[0][0][1], "Сметра")
        with self.assertRaises(ValueError):
            extract(b"a" * 5_000_001, "text/plain")
        writer = __import__("pypdf").PdfWriter()
        for _ in range(13):
            writer.add_blank_page(width=200, height=200)
        stream = io.BytesIO()
        writer.write(stream)
        pages, truncated = extract(stream.getvalue(), "application/pdf")
        self.assertEqual(len(pages), 12)
        self.assertTrue(truncated)

    def test_subprocess_parent_enforces_timeout_and_json_size(self):
        from backend.file_processing import isolated_extract

        with patch(
            "backend.file_processing.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=b"a" * 800_001),
        ) as run:
            with self.assertRaises(ValueError):
                isolated_extract(b"a", "text/plain")
        self.assertEqual(run.call_args.kwargs["timeout"], 25)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertNotIn("ASSISTANT_WORKER_SECRET", run.call_args.kwargs["env"])
        self.assertNotIn("DATABASE_URL", run.call_args.kwargs["env"])

    def test_active_content_hidden_in_pdf_object_is_rejected(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, TextStringObject
        from backend.file_extractor import validate_pdf

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
            {
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): TextStringObject("alert(1)"),
            }
        )
        stream = io.BytesIO()
        writer.write(stream)
        with self.assertRaises(ValueError):
            validate_pdf(stream.getvalue())
