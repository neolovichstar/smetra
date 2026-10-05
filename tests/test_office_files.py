import base64
import io
import os
import unittest
from unittest.mock import patch
import zipfile

from backend.office_documents import DOCX, XLSX, CSV, archive, preview
from tests import office_fixtures, test_business
from tests.test_assistant_jobs import SECRET, worker_token


class OfficeParserTests(unittest.TestCase):
    def test_docx_preserves_text_and_table_as_plain_data(self):
        result = preview(office_fixtures.docx("<script>alert(1)</script>", [["Цена", "15000"]]), DOCX)
        self.assertEqual(result["blocks"][0]["text"], "<script>alert(1)</script>")
        self.assertEqual(result["blocks"][1]["rows"], [["Цена", "15000"]])
        self.assertFalse(result["truncated"])

    def test_excel_keeps_sheets_and_formula_literal(self):
        result = preview(office_fixtures.xlsx(), XLSX)
        self.assertEqual([sheet["name"] for sheet in result["sheets"]], ["Работы", "Материалы"])
        self.assertEqual(result["sheets"][0]["rows"][1]["cells"][1], "15000")
        self.assertIn("не рассчитана", result["sheets"][0]["rows"][2]["cells"][2])
        self.assertFalse(result["truncated"])

    def test_excel_caps_rows_and_columns_and_marks_partial(self):
        result = preview(office_fixtures.xlsx(120, 24), XLSX)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["sheets"][0]["rows"]), 100)
        self.assertTrue(all(len(row["cells"]) <= 20 for row in result["sheets"][0]["rows"]))
        self.assertEqual(len(result["sheets"][0]["rows"][-1]["cells"]), 20)

    def test_docx_caps_blocks_and_marks_partial(self):
        result = preview(office_fixtures.docx(paragraphs=450), DOCX)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["blocks"]), 400)

    def test_csv_semicolon_utf8_bom_and_quoted_delimiter(self):
        result = preview('\ufeffРабота;Цена\n"Покраска; стены";15000\n'.encode(), CSV)
        self.assertEqual(result["sheets"][0]["rows"][1]["cells"], ["Покраска; стены", "15000"])

    def test_csv_is_bounded_and_invalid_utf8_is_rejected(self):
        result = preview(('Name,Price\n' + '\n'.join('Work'+str(i)+',100' for i in range(130))).encode(), CSV)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["sheets"][0]["rows"]), 100)
        for raw in (b'\xff', b'a\0b'):
            with self.assertRaises(ValueError):
                preview(raw, CSV)

    def test_active_external_and_path_content_rejected(self):
        raw = office_fixtures.docx()
        changes = [
            {"word/vbaProject.bin": b"macro"},
            {"word/embeddings/object.bin": b"ole"},
            {"../outside.xml": b"<x/>"},
            {"word/_rels/document.xml.rels": '<Relationships><Relationship TargetMode="External" Type="remote-image" Target="https://example.invalid/image"/></Relationships>'},
            {"word/document.xml": '<!DOCTYPE x [<!ENTITY a "secret">]><x>&a;</x>'},
            {"word/document.xml": '<x/>'.encode('utf-16')},
        ]
        for change in changes:
            with self.subTest(change=list(change)), self.assertRaises(ValueError):
                archive(office_fixtures.rewrite(raw, change), DOCX)

    def test_hyperlink_is_not_fetched_and_preview_remains_plain(self):
        raw = office_fixtures.rewrite(office_fixtures.docx("Link text"), {
            "word/_rels/document.xml.rels": '<Relationships><Relationship TargetMode="External" Type="https://example.invalid/hyperlink" Target="https://example.invalid/never-fetch"/></Relationships>'})
        self.assertEqual(preview(raw, DOCX)["blocks"][0]["text"], "Link text")

    def test_zip_bomb_duplicate_and_type_mismatch_are_rejected(self):
        raw = office_fixtures.docx()
        with self.assertRaises(ValueError):
            archive(office_fixtures.rewrite(raw, {"word/large.xml": b'<x>'+b'A'*1000000+b'</x>'}), DOCX)
        with self.assertRaises(ValueError):
            archive(raw, XLSX)
        output = io.BytesIO(raw)
        with zipfile.ZipFile(output, "a") as duplicate:
            with self.assertWarns(UserWarning):
                duplicate.writestr("word/document.xml", "<x/>")
        with self.assertRaises(ValueError):
            archive(output.getvalue(), DOCX)


class OfficeFileFlows(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def upload(self, owner, name, raw):
        status, result = self.call('/files', 'POST', {'assistant_upload': True, 'name': name,
            'content': base64.b64encode(raw).decode()}, owner)
        self.assertEqual(status, 201, result)
        return result['file']

    def test_upload_preview_download_and_workspace_isolation(self):
        owner, _ = self.account('office-owner')
        other, _ = self.account('office-other')
        for name, raw, mime in [('brief.docx', office_fixtures.docx(), DOCX),
                                ('prices.xlsx', office_fixtures.xlsx(), XLSX),
                                ('prices.csv', b'Name,Price\nWork,15000', CSV)]:
            file = self.upload(owner, name, raw)
            self.assertEqual(file['mime'], mime)
            path = '/files/' + file['id']
            status, result = self.call(path+'/preview', token=owner)
            self.assertEqual(status, 200, result)
            self.assertEqual(result['sha256'], file['sha256'])
            self.assertEqual(self.call(path, token=owner, raw=True)[1], raw)
            self.assertEqual(self.call(path+'/preview', token=other)[0], 404)
            self.assertEqual(self.call(path+'/preview', 'POST', {}, owner)[0], 405)
            metadata = self.call(path+'/metadata', token=owner)[1]
            self.assertTrue(metadata['processing']['supported'])

    def test_invalid_upload_is_not_saved(self):
        owner, _ = self.account('office-invalid')
        for name, raw in [('wrong.docx', b'not a zip'), ('wrong.xlsx', office_fixtures.docx()),
                           ('wrong.csv', b'\xff'), ('wrong.docm', office_fixtures.docx()),
                           ('macro.docx', office_fixtures.rewrite(office_fixtures.docx(), {'word/vbaProject.bin': b'x'}))]:
            status, _ = self.call('/files', 'POST', {'assistant_upload': True, 'name': name,
                'content': base64.b64encode(raw).decode()}, owner)
            self.assertEqual(status, 400)
        self.assertEqual(self.call('/files', token=owner)[1]['items'], [])

    def test_background_index_search_and_assistant_excerpts_without_model_charge(self):
        owner, _ = self.account('office-index')
        with patch.dict(os.environ, ASSISTANT_WORKER_SECRET=SECRET):
            with self.mod.db() as con:
                con.execute('DELETE FROM assistant_jobs')
            file = self.upload(owner, 'prices.xlsx', office_fixtures.xlsx())
            status = self.call('/files/'+file['id']+'/metadata', token=owner)[1]['processing']
            self.assertEqual(status['state'], 'queued')
            with patch('backend.assistant.query_model') as model:
                status, result = self.call('/cron/assistant', token=worker_token())
            self.assertEqual(status, 200, result)
            model.assert_not_called()
        status = self.call('/files/'+file['id']+'/metadata', token=owner)[1]['processing']
        self.assertEqual(status['state'], 'ready', status)
        self.assertEqual(self.call('/assistant', token=owner)[1]['quota']['used'], 0)
        result = self.call('/search?q=15000', token=owner)[1]
        self.assertTrue(any(item.get('file_id') == file['id'] for item in result['items']))
        from backend.business import Service
        from backend.assistant_files import read_file
        with self.mod.db() as con:
            user = con.execute('SELECT * FROM users WHERE email=?', ('office-index@test.invalid',)).fetchone()
            service = Service(None, con, 'http://localhost')
            service.user, service.wid = user, con.execute('SELECT id FROM workspaces WHERE owner_id=?', (user['id'],)).fetchone()[0]
            result = read_file(service, file['id'])
        self.assertIn('Лист: Работы', result['excerpts'][0]['text'])
        self.assertIn('лист таблицы', result['note'])
