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
            "pages": [(1, base64.b64encode(b"\xff\xd8\xffjpeg-page").decode()),
                      (2, base64.b64encode(b"\xff\xd8\xffjpeg-page-2").decode())],
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
        self.assertEqual(len(payload["messages"][1]["content"]), 5)
        self.assertIn("1, 2", payload["messages"][1]["content"][0]["text"])
        self.assertEqual(result['page_numbers'], [1, 2])

    def test_selected_late_pages_and_detail_are_bound_to_real_sources(self):
        row = {'id': 'file', 'name': 'design.pdf', 'mime': 'application/pdf', 'sha256': 'hash'}
        service = SimpleNamespace(get=lambda *_: row, user={'id': 'owner'},
            h=SimpleNamespace(throttle=MagicMock()), wid='workspace',
            con=SimpleNamespace(execute=MagicMock(side_effect=AssertionError('PDF index changed'))))
        rendered = {'pages': [[7, base64.b64encode(b'\xff\xd8\xffpage').decode()]],
                    'total_pages': 20, 'truncated': True}
        response = {'choices': [{'message': {'content': 'Лист 7: читаемый размер 1200 мм.'}}],
                    'usage': {'total_tokens': 123}}
        from backend import ai_tokens
        ai_tokens.start_meter()
        with patch.dict(os.environ, OPENROUTER_API_KEY='test'), patch('backend.attachments.download',
                return_value=SimpleNamespace(data=b'pdf')), patch('backend.file_processing.isolated_extract',
                return_value=rendered) as render, patch('backend.design_vision.urllib.request.urlopen',
                return_value=io.BytesIO(json.dumps(response).encode())) as provider:
            result = analyze(service, 'file', pages=[7], region={'x': .5, 'y': 0, 'width': .5, 'height': .5},
                             focus='Проверь размеры санузла')
        mode = render.call_args.args[1]
        self.assertEqual(json.loads(mode.split(':', 1)[1]), {'pages': [7], 'region': [.5, 0, .5, .5]})
        self.assertEqual(result['page_numbers'], [7])
        self.assertTrue(result['truncated'])
        payload = json.loads(provider.call_args.args[0].data)
        self.assertIn('санузла', payload['messages'][1]['content'][0]['text'])
        self.assertIn('страница 7', payload['messages'][1]['content'][1]['text'])
        self.assertEqual(ai_tokens.metered(), 123)
        service.con.execute.assert_not_called()

    def test_invalid_selection_never_downloads_or_calls_model(self):
        from backend.business import DomainError
        service = SimpleNamespace(get=lambda *_: {'mime': 'application/pdf'})
        with patch('backend.attachments.download') as download:
            for args in ({'pages': []}, {'pages': [True]}, {'pages': [1, 1]}, {'pages': [101]},
                         {'region': {'x': 0, 'y': 0, 'width': .01, 'height': 1}},
                         {'region': {'x': .8, 'y': 0, 'width': .5, 'height': 1}},
                         {'region': {'x': float('nan'), 'y': 0, 'width': 1, 'height': 1}}):
                with self.subTest(args=args), self.assertRaises(DomainError) as error:
                    analyze(service, 'file', **args)
                self.assertEqual(error.exception.status, 400)
        download.assert_not_called()
