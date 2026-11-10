"""Real bounded parsers, source navigation and tenant isolation for AI files."""

import base64
import io
import json
import os
import unittest
from unittest.mock import patch

from backend.assistant_files import describe_file, read_file, search_content
from backend.business import DomainError
from backend.file_extractor import extract, render_scans
from backend.office_documents import DOCX, XLSX, CSV, preview, text_sections
from tests import office_fixtures, test_business, test_file_processing


class DocumentParserTests(unittest.TestCase):
    def test_pdf_reads_page_after_twelve_with_real_text_and_paragraphs(self):
        from reportlab.pdfgen.canvas import Canvas
        output = io.BytesIO()
        canvas = Canvas(output)
        for number in range(1, 19):
            canvas.drawString(50, 750, f'Page {number}: specification')
            canvas.drawString(50, 720, f'Quantity {number * 10}')
            canvas.showPage()
        canvas.save()
        pages, truncated = extract(output.getvalue(), 'application/pdf')
        self.assertEqual(len(pages), 18)
        self.assertIn('Quantity 180', pages[17][1])
        self.assertIn('\n', pages[17][1])
        self.assertFalse(truncated)

    def test_excel_assistant_reads_late_rows_and_retains_coordinates(self):
        content = office_fixtures.xlsx(180, 24)
        self.assertTrue(preview(content, XLSX)['truncated'])
        result = preview(content, XLSX, for_assistant=True)
        sections = text_sections(result)
        self.assertIn('Строка 180:', sections[0][1])
        self.assertIn('A="Позиция 179"', sections[0][1])
        self.assertIn('X=', sections[0][1])
        self.assertIn('сохранённого результата нет', sections[0][1])
        self.assertFalse(result['truncated'])

    def test_cached_excel_result_is_labelled_as_unverified_and_not_recalculated(self):
        content = office_fixtures.xlsx()
        import zipfile
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            xml = package.read('xl/worksheets/sheet1.xml')
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        namespace = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        for cell in root.iter(namespace + 'c'):
            if cell.get('r') == 'C3':
                cell.find(namespace + 'v').text = '17000'
        content = office_fixtures.rewrite(content, {'xl/worksheets/sheet1.xml': ET.tostring(root)})
        pages, _ = extract(content, XLSX)
        self.assertIn('может быть устаревшим): 17000', pages[0][1])
        self.assertIn('=SUM(B2:B3)', pages[0][1])

    def test_docx_and_csv_keep_rows_and_cell_boundaries(self):
        pages, partial = extract(office_fixtures.docx('ТЗ\nОтделка', [['Материал', 'Цена'], ['Краска', '1200']]), DOCX)
        self.assertIn('ТЗ\nОтделка', pages[0][1])
        self.assertIn('Таблица 1, строка 2: A="Краска" | B="1200"', pages[0][1])
        self.assertFalse(partial)
        pages, _ = extract('Материал;Цена\n"Краска; белая";1200'.encode(), CSV)
        self.assertIn('Строка 2: A="Краска; белая" | B="1200"', pages[0][1])

    def test_text_global_bound_and_line_breaks(self):
        pages, partial = extract(('Заголовок\nA\tB\n' + 'я' * 160_000).encode(), 'text/plain')
        self.assertTrue(partial)
        self.assertLessEqual(sum(len(text) for _, text in pages), 120_000)
        self.assertIn('\nA\tB\n', pages[0][1])

    def test_selected_pdf_crop_is_top_left_and_high_resolution(self):
        from reportlab.pdfgen.canvas import Canvas
        from PIL import Image
        output = io.BytesIO()
        canvas = Canvas(output, pagesize=(200, 200))
        canvas.setFillColorRGB(1, 0, 0)
        canvas.rect(100, 100, 100, 100, fill=1, stroke=0)
        canvas.showPage()
        canvas.showPage()
        canvas.save()
        result = render_scans(output.getvalue(), {'pages': [1], 'region': [.5, 0, .5, .5]})
        self.assertEqual([number for number, _ in result['pages']], [1])
        self.assertTrue(result['truncated'])
        with Image.open(io.BytesIO(base64.b64decode(result['pages'][0][1]))) as image:
            self.assertEqual(image.size, (2200, 2200))
            red, green, blue = image.getpixel((1100, 1100))
            self.assertGreater(red, 240)
            self.assertLess(green + blue, 20)

    def test_large_picture_is_bounded_for_vision_without_changing_source(self):
        import random
        from PIL import Image
        from backend.design_vision import prepare_image
        output = io.BytesIO()
        with Image.frombytes('L', (1600, 1600), random.Random(17).randbytes(1600 * 1600)) as image:
            image.save(output, 'PNG')
        raw = output.getvalue()
        self.assertGreater(len(raw), 1_500_000)
        prepared = prepare_image(raw)
        self.assertLess(len(prepared), 1_500_000)
        self.assertTrue(raw.startswith(b'\x89PNG'))
        self.assertTrue(prepared.startswith(b'\xff\xd8\xff'))


class DocumentNavigationTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account
    service = test_file_processing.FileProcessingTests.service

    def upload(self, owner, text, name='brief.txt'):
        code, result = self.call('/files', 'POST', {'assistant_upload': True, 'name': name,
            'content': base64.b64encode(text.encode()).decode()}, owner)
        self.assertEqual(code, 201, result)
        return result['file']

    def test_read_continues_without_gaps_and_preserves_lines(self):
        owner, _ = self.account('navigation')
        text = '\n'.join(f'Строка {number}: материал {number * 2}' for number in range(1000))
        file = self.upload(owner, text)
        service = self.service(owner)
        arguments, chunks = {}, []
        for _ in range(10):
            result = read_file(service, file['id'], **arguments)
            chunks.extend(item['text'] for item in result['excerpts'])
            if not result['has_more']:
                break
            arguments = {key: value for key, value in result['next_read'].items() if key != 'id'}
        self.assertEqual(''.join(chunks), text)
        self.assertEqual(result['source_type'], 'fragment')
        self.assertFalse(result['index_partial'])

    def test_cursor_rejects_changed_source_and_different_file(self):
        owner, _ = self.account('cursor-version')
        file = self.upload(owner, 'old\n' * 6000)
        other = self.upload(owner, 'other\n' * 5000)
        service = self.service(owner)
        cursor = read_file(service, file['id'])['next_cursor']
        with self.assertRaises(DomainError) as error:
            read_file(service, other['id'], cursor=cursor)
        self.assertEqual(error.exception.status, 409)
        service.con.execute('UPDATE files SET sha256=? WHERE id=?', ('new-source', file['id']))
        with self.assertRaises(DomainError) as error:
            read_file(service, file['id'], cursor=cursor)
        self.assertEqual(error.exception.status, 409)

    def test_query_finds_late_cyrillic_terms_and_search_ranks_multiple_words(self):
        owner, _ = self.account('russian-search')
        self.upload(owner, 'КРАСКА для потолка')
        file = self.upload(owner, 'Начало\n' + 'Описание\n' * 2500 + 'КРАСКА для СТЕН: 1200 ₽')
        service = self.service(owner)
        result = read_file(service, file['id'], 'краска стены')
        self.assertIn('1200', result['excerpts'][0]['text'])
        self.assertGreater(result['excerpts'][0]['start_offset'], 1400)
        self.assertEqual(search_content(service, 'краска стен')['items'][0]['file_id'], file['id'])

    def test_secret_is_redacted_before_excerpt_and_cursor_boundaries(self):
        owner, _ = self.account('secret-boundary')
        secret = 'secretvalue123456789'
        file = self.upload(owner, 'a' * 11990 + ' API_KEY=' + secret + '\nWarranty 12 months')
        service = self.service(owner)
        first = read_file(service, file['id'])
        second = read_file(service, file['id'], cursor=first['next_cursor'])
        self.assertNotIn(secret, json.dumps([first, second]))
        self.assertNotIn(secret, json.dumps(search_content(service, 'secretvalue')))

    def test_source_inventory_and_explicit_sheet_page(self):
        owner, _ = self.account('sources')
        file = self.upload(owner, 'placeholder')
        service = self.service(owner)
        service.con.execute('DELETE FROM file_text_chunks WHERE file_id=?', (file['id'],))
        for page in (1, 17, 18):
            service.con.execute('INSERT INTO file_text_chunks(file_id,workspace_id,page,text,source_sha256) VALUES(?,?,?,?,?)',
                                (file['id'], service.wid, page, f'Page {page} data', file['sha256']))
        service.con.execute('UPDATE files SET mime=?,index_pages=18,index_truncated=1 WHERE id=?',
                            ('application/pdf', file['id']))
        info = describe_file(service, file['id'])
        self.assertEqual(info['total_sources'], 18)
        self.assertEqual(info['indexed_sources'], 3)
        self.assertTrue(info['index_partial'])
        result = read_file(service, file['id'], page=17)
        self.assertEqual([part['page'] for part in result['excerpts']], [17])

    def test_foreign_workspace_and_invalid_cursor_are_rejected(self):
        owner, _ = self.account('source-owner')
        stranger, _ = self.account('source-stranger')
        self.call('/dashboard', token=stranger)
        file = self.upload(owner, 'Private specification')
        foreign = self.service(stranger)
        for function in (read_file, describe_file):
            with self.assertRaises(DomainError) as error:
                function(foreign, file['id'])
            self.assertEqual(error.exception.status, 404)
        self.assertEqual(search_content(foreign, 'private')['items'], [])
        service = self.service(owner)
        for args in ({'cursor': '!invalid'}, {'page': True}, {'page': 101}, {'cursor': 123}):
            with self.subTest(args=args), self.assertRaises(DomainError) as error:
                read_file(service, file['id'], **args)
            self.assertEqual(error.exception.status, 400)

    def test_scanned_pdf_can_enter_visual_chat_but_text_stays_explicitly_unavailable(self):
        from backend.file_processing import ensure_ready
        owner, _ = self.account('scan-visual')
        file = self.upload(owner, 'placeholder')
        service = self.service(owner)
        service.con.execute('DELETE FROM file_text_chunks WHERE file_id=?', (file['id'],))
        service.con.execute("UPDATE files SET mime='application/pdf',index_status='needs_ocr',index_pages=9,index_truncated=1 WHERE id=?", (file['id'],))
        context = {'entity': 'files', 'id': file['id']}
        ensure_ready(service, context, allow_visual=True)
        with self.assertRaises(DomainError):
            read_file(service, file['id'])
        with patch.dict(os.environ, OPENROUTER_API_KEY='test'), patch('backend.assistant.query_model',
                return_value={'content': 'Для проверки плана нужны страницы PDF.'}):
            status, result = self.call('/assistant/chat', 'POST', {'text': 'Проверь дизайн-проект', 'context': context}, owner)
        self.assertEqual(status, 200, result)

    def test_background_assistant_combines_late_pdf_text_and_selected_visual_page(self):
        from reportlab.pdfgen.canvas import Canvas
        from tests.test_assistant_jobs import SECRET, worker_token
        owner, _ = self.account('design-worker')
        output = io.BytesIO()
        canvas = Canvas(output)
        for number in range(1, 19):
            canvas.drawString(50, 750, f'Sheet {number}: bathroom wall 1200 mm')
            canvas.showPage()
        canvas.save()
        with patch.dict(os.environ, OPENROUTER_API_KEY='test', ASSISTANT_WORKER_SECRET=SECRET):
            code, uploaded = self.call('/files', 'POST', {'assistant_upload': True, 'name': 'design.pdf',
                'content': base64.b64encode(output.getvalue()).decode()}, owner)
            self.assertEqual(code, 201, uploaded)
            file_id = uploaded['file']['id']
            self.assertEqual(self.call('/cron/assistant', token=worker_token())[0], 200)
            arguments = [
                ('get_file_metadata', {'id': file_id}),
                ('read_file', {'id': file_id, 'page': 17}),
                ('analyze_design_image', {'id': file_id, 'pages': [17], 'focus': 'Проверь размер стены санузла'}),
            ]
            observed = []
            def model(messages):
                observed.append(json.loads(json.dumps(messages)))
                if len(observed) <= len(arguments):
                    name, args = arguments[len(observed) - 1]
                    return {'tool_calls': [{'id': f'tool-{len(observed)}', 'type': 'function',
                        'function': {'name': name, 'arguments': json.dumps(args)}}]}
                return {'content': 'На странице 17 design.pdf указан размер 1200 мм; остальные листы визуально не проверены.'}
            response = {'choices': [{'message': {'content': 'Страница 17: подпись 1200 mm.'}}],
                        'usage': {'total_tokens': 120}}
            code, queued = self.call('/assistant/jobs', 'POST', {'text': 'Проверь лист 17 дизайн-проекта',
                'context': {'entity': 'files', 'id': file_id}}, owner, key='design-review')
            self.assertEqual(code, 202, queued)
            import urllib.request
            original_open = urllib.request.urlopen
            def open_request(request, *args, **kwargs):
                if getattr(request, 'full_url', '').startswith('https://openrouter.ai/'):
                    return io.BytesIO(json.dumps(response).encode())
                return original_open(request, *args, **kwargs)
            with patch('backend.assistant.query_model', side_effect=model), patch(
                    'backend.design_vision.urllib.request.urlopen', side_effect=open_request):
                self.assertEqual(self.call('/cron/assistant', token=worker_token())[0], 200)
            job_id = queued['job']['id'] if 'job' in queued else queued['id']
            _, completed = self.call('/assistant/jobs/' + job_id, token=owner)
        self.assertEqual(completed['job']['status'], 'completed', completed)
        metadata = json.loads(next(item['content'] for item in observed[1] if item.get('role') == 'tool'))
        self.assertEqual(metadata['analysis']['total_sources'], 18)
        text = json.loads([item['content'] for item in observed[2] if item.get('role') == 'tool'][-1])
        self.assertEqual(text['excerpts'][0]['page'], 17)
        self.assertIn('1200', text['excerpts'][0]['text'])
        visual = json.loads([item['content'] for item in observed[3] if item.get('role') == 'tool'][-1])
        self.assertEqual(visual['page_numbers'], [17])
        self.assertTrue(visual['truncated'])

    def test_legacy_twelve_page_index_is_reread_once_without_rewriting_the_document(self):
        from reportlab.pdfgen.canvas import Canvas
        from backend.assistant_files import extract_pages
        owner, _ = self.account('legacy-design')
        output = io.BytesIO()
        canvas = Canvas(output)
        for number in range(1, 19):
            canvas.drawString(50, 750, f'Sheet {number}: material specification')
            canvas.showPage()
        canvas.save()
        code, result = self.call('/files', 'POST', {'assistant_upload': True, 'name': 'old-design.pdf',
            'content': base64.b64encode(output.getvalue()).decode()}, owner)
        self.assertEqual(code, 201, result)
        file = result['file']
        service = self.service(owner)
        service.con.execute('DELETE FROM file_text_chunks WHERE file_id=? AND page>12', (file['id'],))
        service.con.execute("UPDATE files SET index_method='text',index_version=1,index_pages=12,index_truncated=1 WHERE id=?", (file['id'],))
        self.assertTrue(describe_file(service, file['id'])['legacy_index'])
        with patch('backend.assistant_files.extract_pages', wraps=extract_pages) as extract_again:
            first = read_file(service, file['id'], page=17)
            second = read_file(service, file['id'], page=18)
        self.assertEqual(extract_again.call_count, 1)
        self.assertIn('Sheet 17', first['excerpts'][0]['text'])
        self.assertIn('Sheet 18', second['excerpts'][0]['text'])
        self.assertEqual(first['total_sources'], 18)
        self.assertFalse(first['index_partial'])
        self.assertEqual(service.con.execute('SELECT count(*) FROM file_text_chunks WHERE file_id=?', (file['id'],)).fetchone()[0], 12)
        self.assertEqual(service.get('files', file['id'])['sha256'], file['sha256'])


@unittest.skipUnless(os.getenv('SMETRA_TEST_ADMIN_URL') and os.getenv('SMETRA_TEST_RUNTIME_URL'),
                     'requires disposable PostgreSQL schema 74')
class DocumentNavigationPostgresTests(DocumentNavigationTests):
    from tests import test_protected_estimates as _pg
    tearDownClass = classmethod(_pg.ProtectedEstimatePostgresTests.tearDownClass.__func__)

    @classmethod
    def setUpClass(cls):
        from tests.document_postgres_fixture import prepare
        prepare(os.environ['SMETRA_TEST_ADMIN_URL'])
        cls._pg.ProtectedEstimatePostgresTests.setUpClass.__func__(cls)

    def setUp(self):
        self.created_users = []
        with self.mod.db() as con:
            con.execute('DELETE FROM rate_limits')
        super().setUp()

    def account(self, name, **kwargs):
        import uuid
        result = super().account(name + '-pg-' + uuid.uuid4().hex[:8], **kwargs)
        self.created_users.append(result[1])
        return result

    def tearDown(self):
        self.doCleanups()
        with self.mod.db() as con:
            for user_id in self.created_users:
                con.execute('DELETE FROM workspaces WHERE owner_id=?', (user_id,))
                con.execute('DELETE FROM users WHERE id=?', (user_id,))


if __name__ == '__main__':
    unittest.main()
