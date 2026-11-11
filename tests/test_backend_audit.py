"""Regression tests for request trust boundaries and credential revocation."""

import base64
import io
import json
import subprocess
import unittest
from email.message import Message
from unittest.mock import patch

from backend import app
from backend.ai import capture_file
from backend.business import DomainError
from tests import test_business as business_flows


class JsonBoundaryTests(unittest.TestCase):
    def parse(self, raw, length=None):
        request = app.Handler.__new__(app.Handler)
        request.headers = Message()
        request.headers["Content-Type"] = "application/json"
        request._body_length = len(raw) if length is None else length
        request.rfile = io.BytesIO(raw)
        return request.body()

    def test_rejects_numeric_overflow_and_invalid_unicode(self):
        for raw in (b'{"v":1e999}', b'{"v":-1e999}',
                    b'{"v":"\\ud800"}', b'{"v":"\\u0000"}',
                    b'{"\\udfff":1}'):
            with self.subTest(raw=raw):
                with self.assertRaises(app.ApiError) as error:
                    self.parse(raw)
                self.assertEqual(error.exception.status, 400)

    def test_bounds_nested_containers_and_handles_parser_recursion(self):
        for depth in (65, 1500):
            raw = b'{"v":' + b'[' * depth + b'0' + b']' * depth + b'}'
            with self.subTest(depth=depth):
                with self.assertRaises(app.ApiError) as error:
                    self.parse(raw)
                self.assertEqual(error.exception.status, 400)

    def test_rejects_truncated_request_instead_of_accepting_empty_object(self):
        for raw in (b"", b"{}"):
            with self.subTest(raw=raw):
                with self.assertRaises(app.ApiError) as error:
                    self.parse(raw, length=10)
                self.assertEqual(error.exception.status, 400)

    def test_keeps_valid_unicode_numbers_and_nested_data(self):
        value = {"text": "Сметра 😀", "amount": 1.5, "items": [{"ok": True}]}
        self.assertEqual(self.parse(json.dumps(value).encode()), value)
        self.assertEqual(self.parse(b""), {})


class CredentialBoundaryTests(unittest.TestCase):
    setUpClass = classmethod(business_flows.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(business_flows.BusinessFlows.tearDownClass.__func__)
    setUp = business_flows.BusinessFlows.setUp
    call = business_flows.BusinessFlows.call
    account = business_flows.BusinessFlows.account

    def test_malformed_authorization_never_falls_back_to_cookie(self):
        from tests.test_security_hardening import SecurityHardeningTests
        token, _ = self.account("audit-cookie")
        cookie = "session=" + token
        request = SecurityHardeningTests.request
        for authorization in ("Bearer ", "Basic irrelevant", "Bearer a b"):
            with self.subTest(authorization=authorization):
                code, _, _ = request(self, "GET", "/api/me", headers={
                    "Cookie": cookie, "Authorization": authorization,
                })
                self.assertEqual(code, 401)
        code, _, _ = request(self, "GET", "/api/me", headers={
            "Authorization": "bearer " + token,
        })
        self.assertEqual(code, 200)

    def test_empty_bearer_cannot_bypass_cookie_origin_check(self):
        from tests.test_security_hardening import SecurityHardeningTests
        token, _ = self.account("audit-origin")
        code, _, _ = SecurityHardeningTests.request(self, "POST", "/api/auth/logout", headers={
            "Cookie": "session=" + token, "Authorization": "Bearer ",
        })
        self.assertIn(code, (401, 403))
        self.assertEqual(self.call("/me", token=token)[0], 200)

    def test_reset_revokes_all_preexisting_reset_links_and_sessions(self):
        token, user_id = self.account("audit-reset")
        with self.mod.db() as con:
            first = self.mod.create_email_token(con, user_id, "reset", 1800)
            second = self.mod.create_email_token(con, user_id, "reset", 1800)
        password = "new secure twelve password"
        self.assertEqual(self.call("/auth/reset/confirm", "POST", {
            "token": first, "password": password,
        })[0], 200)
        self.assertEqual(self.call("/auth/reset/confirm", "POST", {
            "token": second, "password": "attacker replacement password",
        })[0], 400)
        self.assertEqual(self.call("/me", token=token)[0], 401)
        self.assertEqual(self.call("/auth/login", "POST", {
            "email": "audit-reset@test.invalid", "password": password,
        })[0], 200)


class CaptureIsolationTests(unittest.TestCase):
    def test_document_capture_uses_bounded_worker(self):
        with patch("backend.file_processing.isolated_extract",
                   return_value={"text": "Покраска стены", "image_url": ""}) as worker:
            result = capture_file({"name": "source.pdf", "mime": "application/pdf",
                                   "content": base64.b64encode(b"%PDF-fixture").decode()})
        self.assertEqual(result, ("Покраска стены", ""))
        worker.assert_called_once_with(b"%PDF-fixture", "capture:application/pdf")

    def test_parser_timeout_is_a_client_error(self):
        with patch("backend.file_processing.isolated_extract",
                   side_effect=subprocess.TimeoutExpired("parser", 25)):
            with self.assertRaises(DomainError) as error:
                capture_file({"name": "source.pdf", "mime": "application/pdf",
                              "content": base64.b64encode(b"%PDF-fixture").decode()})
        self.assertEqual(error.exception.status, 400)

    def test_plain_text_capture_preserves_unicode(self):
        text, image = capture_file({"name": "source.txt", "mime": "text/plain",
                                   "content": base64.b64encode("Работа: покраска".encode()).decode()})
        self.assertEqual(text, "Работа: покраска")
        self.assertEqual(image, "")


    def capture(self, name, mime, raw):
        return capture_file({"name": name, "mime": mime,
                             "content": base64.b64encode(raw).decode()})

    def test_real_pdf_and_office_documents_are_read_in_worker(self):
        from reportlab.pdfgen.canvas import Canvas
        from backend.office_documents import DOCX, XLSX, CSV
        from tests import office_fixtures

        output = io.BytesIO()
        canvas = Canvas(output)
        canvas.drawString(40, 700, "Painting wall 15000")
        canvas.save()
        self.assertIn("Painting wall", self.capture("brief.pdf", "application/pdf", output.getvalue())[0])
        self.assertIn("Покраска", self.capture("brief.docx", DOCX, office_fixtures.docx("Покраска"))[0])
        self.assertIn("15000", self.capture("prices.xlsx", XLSX, office_fixtures.xlsx())[0])
        self.assertIn("15000", self.capture("prices.csv", CSV, b"Work,Price\nPaint,15000")[0])

    def test_capture_rejects_active_pdf_and_over_page_limit(self):
        from pypdf import PdfWriter

        for pages, script in ((1, "app.alert('fixture')"), (13, None)):
            writer = PdfWriter()
            for _ in range(pages):
                writer.add_blank_page(width=100, height=100)
            if script:
                writer.add_js(script)
            output = io.BytesIO()
            writer.write(output)
            with self.subTest(pages=pages, script=script), self.assertRaises(DomainError):
                self.capture("unsafe.pdf", "application/pdf", output.getvalue())

    def test_capture_rejects_xml_entities_and_embedded_macros(self):
        from backend.office_documents import DOCX
        from tests import office_fixtures

        original = office_fixtures.docx("Safe source")
        for changes in (
            {"word/vbaProject.bin": b"macro"},
            {"word/document.xml": '<!DOCTYPE x [<!ENTITY a "expanded">]><x>&a;</x>'},
        ):
            with self.subTest(changes=list(changes)), self.assertRaises(DomainError):
                self.capture("unsafe.docx", DOCX, office_fixtures.rewrite(original, changes))
