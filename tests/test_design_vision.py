"""A visual design PDF preview must not overwrite the source document index."""

import base64
import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.design_vision import analyze


class DesignVisionTests(unittest.TestCase):
    def test_pdf_preview_is_bounded_scoped_and_read_only(self):
        row = {
            "id": "user-file", "name": "project.pdf", "mime": "application/pdf",
            "sha256": "file-hash",
        }
        service = SimpleNamespace(
            get=lambda kind, file_id: row if kind == "files" and file_id == "user-file" else None,
            user={"id": "owner"}, h=SimpleNamespace(throttle=MagicMock()),
            con=SimpleNamespace(execute=MagicMock(side_effect=AssertionError("PDF index changed"))),
            wid="workspace",
        )
        result_bytes = json.dumps({
            "choices": [{"message": {"content": "На планировке видна кухня и коридор."}}],
        }).encode()
        pdf_pages = {
            "pages": [(1, base64.b64encode(b"jpeg-page").decode()),
                      (2, base64.b64encode(b"jpeg-page-2").decode())],
            "truncated": True, "total_pages": 9,
        }
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-only"}), patch(
            "backend.attachments.download", return_value=SimpleNamespace(data=b"mock-pdf")
        ), patch(
            "backend.file_processing.isolated_extract", return_value=pdf_pages
        ) as render, patch(
            "backend.design_vision.urllib.request.urlopen",
            return_value=io.BytesIO(result_bytes),
        ) as urlopen:
            result = analyze(service, "user-file")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["total_pages"], 9)
        self.assertEqual(result["analyzed_pages"], 2)
        self.assertIn("кухня", result["analysis"])
        service.con.execute.assert_not_called()
        render.assert_called_once_with(b"mock-pdf", "render-pdf")
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["provider"]["data_collection"], "deny")
        self.assertEqual(len(payload["messages"][1]["content"]), 3)
        self.assertIn("две страницы", payload["messages"][1]["content"][0]["text"])
