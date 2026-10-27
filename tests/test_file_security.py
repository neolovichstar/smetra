"""Regression checks for upload format spoofing, ZIP payloads, and scanner failure."""
import io
import os
import unittest
import zipfile
from unittest.mock import patch

from backend.business import DomainError
from backend.file_security import scan_upload, validate_signature
from backend.office_documents import DOCX, archive


class FileSignatureTests(unittest.TestCase):
    def test_fake_extensions_rejected(self):
        cases = (
            ("virus.png", b"MZ" + b"\x00" * 80),
            ("report.jpg", b"%PDF-1.7\nbody%%EOF"),
            ("contract.pdf", b"PK\x03\x04fake"),
            ("invoice.docx", b"MZ" + b"\x00" * 20),
            ("prices.xlsx", b"not a zip"),
            ("notes.txt", b"\x7fELF" + b"\x00" * 80),
            ("data.csv", b"PK\x03\x04not a csv"),
            ("README.md", b"#!/bin/sh\nrm something"),
            ("file.txt", b"<html><script>alert(1)</script></html>"),
            ("document.txt", b"\xff\xfeH\x00i\x00"),
            ("image.svg", b"<svg/>"),
        )
        for name, data in cases:
            with self.subTest(name=name), self.assertRaises(DomainError):
                validate_signature(name, data)

    def test_real_headers_accepted_then_structurally_validated(self):
        for name, data in (
            ("notes.txt", "Пример безопасного текста\n".encode()),
            ("data.csv", b"name,price\nplaster,190\n"),
            ("README.md", b"# Markdown\n**Hello**"),
            ("manual.pdf", b"%PDF-1.7\n"),
            ("photo.png", b"\x89PNG\r\n\x1a\n"),
            ("photo.jpeg", b"\xff\xd8\xff\xe0"),
            ("file.docx", b"PK\x03\x04"),
        ):
            with self.subTest(name=name):
                validate_signature(name, data)
        # The magic gate alone does not prove that an image, PDF or ZIP is
        # valid; their independent decoders must still reject truncated files.

    @staticmethod
    def docx(extra=None):
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml",
                       '<Types><Override PartName="/word/document.xml" '
                       'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                       '</Types>')
            z.writestr("word/document.xml", "<document><body/></document>")
            if extra:
                z.writestr(extra, b"harmless test")
        return mem.getvalue()

    def test_office_archive_has_no_executable_entry_or_overlay(self):
        base = self.docx()
        validate_signature("demo.docx", base)
        self.assertIn("word/document.xml", archive(base, DOCX))
        with self.assertRaises(ValueError):
            archive(base + b"MZ-trailing-overlay", DOCX)
        with self.assertRaises(ValueError):
            archive(b"MZ" + base, DOCX)
        with self.assertRaises(ValueError):
            archive(self.docx("word/media/update.exe"), DOCX)

    def test_text_blocks_nulls_but_keeps_unicode(self):
        validate_signature("utf8.txt", b"\xef\xbb\xbf" + "Добрый день\n".encode())
        for payload in (b"hello\x00world", b"\x01control", b"report\x7fline"):
            with self.assertRaises(DomainError):
                validate_signature("some.txt", payload)


class ScannerTests(unittest.TestCase):
    class FakeSocket:
        def __init__(self, reply):
            self.reply, self.sent = reply, []
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def settimeout(self, _):
            pass
        def sendall(self, data):
            self.sent.append(bytes(data))
        def recv(self, _):
            return self.reply

    def test_required_scanner_missing_fails_closed(self):
        with patch.dict(os.environ, {"CLAMAV_HOST": "", "FILE_AV_REQUIRED": "1"}):
            with self.assertRaises(DomainError) as error:
                scan_upload(b"hello")
            self.assertEqual(error.exception.status, 503)

    def test_scanner_clean_and_detected(self):
        with patch.dict(os.environ, {"CLAMAV_HOST": "127.0.0.1", "CLAMAV_PORT": "3310"}):
            clean = self.FakeSocket(b"stream: OK\x00")
            with patch("backend.file_security.socket.create_connection", return_value=clean):
                self.assertTrue(scan_upload(b"hello"))
            self.assertEqual(clean.sent[0], b"zINSTREAM\x00")
            self.assertEqual(clean.sent[-1], b"\x00\x00\x00\x00")
            infected = self.FakeSocket(b"stream: Eicar-Test-Signature FOUND\x00")
            with patch("backend.file_security.socket.create_connection", return_value=infected):
                with self.assertRaises(DomainError) as error:
                    scan_upload(b"harmless-test")
            self.assertEqual(error.exception.status, 400)

    def test_configured_scanner_errors_fail_closed(self):
        with patch.dict(os.environ, {"CLAMAV_HOST": "127.0.0.1"}):
            with patch("backend.file_security.socket.create_connection", side_effect=OSError("down")):
                with self.assertRaises(DomainError) as error:
                    scan_upload(b"hello")
            self.assertEqual(error.exception.status, 503)

    def test_without_scanner_reports_no_scan(self):
        with patch.dict(os.environ, {"CLAMAV_HOST": "", "FILE_AV_REQUIRED": "0"}):
            self.assertFalse(scan_upload(b"hello"))
