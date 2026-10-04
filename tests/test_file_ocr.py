"""Bounded PDF OCR, private quotas and atomic source/access/lease fencing."""
import base64
import concurrent.futures
import os
import unittest
from unittest.mock import patch

import test_business
import test_file_processing
from test_assistant_jobs import SECRET, worker_token
from scan_fixture import scan_pdf
from backend.business import DomainError


class FileOcrTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account
    service = test_file_processing.FileProcessingTests.service

    def setUp(self):
        test_business.BusinessFlows.setUp(self)
        env = patch.dict(os.environ, ASSISTANT_WORKER_SECRET=SECRET, OPENROUTER_API_KEY='test-only', OPENROUTER_OCR_MODEL='openrouter/free')
        env.start()
        self.addCleanup(env.stop)
        with self.mod.db() as con:
            con.execute('DELETE FROM assistant_jobs')

    def work(self, text='Paint walls 12 m2. Total 1234.50 RUB.', side_effect=None):
        with patch('backend.file_ocr.request_page', return_value=text, side_effect=side_effect) as model:
            code, result = self.call('/cron/assistant', token=worker_token())
        self.assertEqual(code, 200, result)
        return model

    def upload(self, owner, pages=1, text_pages=(), expected='needs_ocr'):
        code, result = self.call('/files', 'POST', {'assistant_upload': True, 'name': 'scan.pdf', 'content': base64.b64encode(scan_pdf(pages, text_pages)).decode()}, owner)
        self.assertEqual(code, 201, result)
        file = result['file']
        self.work().assert_not_called()
        self.assertEqual(self.info(owner, file)['state'], expected)
        return file

    def info(self, owner, file):
        code, result = self.call('/files/' + file['id'] + '/metadata', token=owner)
        self.assertEqual(code, 200, result)
        return result['processing']

    def enqueue(self, owner, file, key='ocr'):
        code, result = self.call('/files/' + file['id'] + '/ocr', 'POST', {}, owner, key=key)
        self.assertIn(code, (200, 202), result)
        return result['processing']

    def test_real_render_and_index_only_first_two_pages_with_no_chat_quota(self):
        from backend.assistant_files import read_file, search_content
        owner, _ = self.account('ocr-scanned')
        file = self.upload(owner, 3)
        info = self.enqueue(owner, file)
        self.assertEqual(info['ocr_quota']['used'], 1)
        self.assertEqual(info['method'], 'ocr')
        self.assertEqual(self.work().call_count, 2)
        info = self.info(owner, file)
        self.assertEqual(info['state'], 'ready')
        self.assertTrue(info['truncated'])
        self.assertEqual(info['pages'], 2)
        result = read_file(self.service(owner), file['id'])
        self.assertEqual(result['extraction'], 'ocr')
        self.assertIn('OCR', result['note'])
        self.assertTrue(result['truncated'])
        self.assertEqual(search_content(self.service(owner), 'paint')['items'][0]['file_id'], file['id'])
        self.assertEqual(self.call('/assistant', token=owner)[1]['quota']['used'], 0)
        self.assertEqual(self.enqueue(owner, file, 'cached')['ocr_quota']['used'], 1)
        self.work().assert_not_called()

    def test_pending_or_unread_scan_rejects_chat_before_monthly_reservation(self):
        owner, _ = self.account('ocr-no-chat')
        file = self.upload(owner)
        for active in (False, True):
            if active:
                self.enqueue(owner, file)
            for path in ('/assistant/chat', '/assistant/stream', '/assistant/jobs'):
                code, result = self.call(path, 'POST', {'text': 'Read document', 'context': {'entity': 'files', 'id': file['id']}}, owner, key='chat')
                self.assertEqual(code, 409, result)
            self.assertEqual(self.call('/assistant', token=owner)[1]['quota']['used'], 0)

    def test_private_metadata_job_and_wrong_type(self):
        owner, _ = self.account('ocr-private')
        outsider, _ = self.account('ocr-outsider')
        file = self.upload(owner)
        job = self.enqueue(owner, file)['job_id']
        for method in ('GET', 'POST', 'DELETE'):
            self.assertEqual(self.call('/files/' + file['id'] + '/ocr', method, {} if method == 'POST' else None, outsider, key='private')[0], 404)
        self.assertEqual(self.call('/assistant/jobs/' + job, token=outsider)[0], 404)
        txt = self.call('/files', 'POST', {'assistant_upload': True, 'name': 'note.txt', 'content': base64.b64encode(b'text').decode()}, owner)[1]['file']
        self.assertEqual(self.call('/files/' + txt['id'] + '/ocr', 'POST', {}, owner, key='txt')[0], 422)

    def test_parallel_replay_and_changed_request_key(self):
        owner, _ = self.account('ocr-parallel')
        file = self.upload(owner)
        other = self.upload(owner)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: self.call('/files/' + file['id'] + '/ocr', 'POST', {}, owner, key='same'), range(4)))
        self.assertTrue(all(code in (200, 202) for code, _ in values), values)
        self.assertEqual(len({r['processing']['job_id'] for _, r in values}), 1)
        self.assertEqual(self.info(owner, file)['ocr_quota']['used'], 1)
        self.assertEqual(self.call('/files/' + other['id'] + '/ocr', 'POST', {}, owner, key='same')[0], 409)

    def test_queued_cancel_refunds_once_and_manual_retry_works(self):
        owner, _ = self.account('ocr-cancel')
        file = self.upload(owner)
        self.enqueue(owner, file)
        for _ in range(2):
            result = self.call('/files/' + file['id'] + '/ocr', 'DELETE', token=owner)[1]['processing']
            self.assertEqual(result['ocr_quota']['used'], 0)
        self.work().assert_not_called()
        self.enqueue(owner, file, 'retry')
        self.work()
        self.assertEqual(self.info(owner, file)['state'], 'ready')

    def test_inflight_cancel_stops_second_page_and_writes_nothing(self):
        owner, _ = self.account('ocr-inflight')
        file = self.upload(owner, 2)
        self.enqueue(owner, file)

        def model(_image):
            self.assertEqual(self.call('/files/' + file['id'] + '/ocr', 'DELETE', token=owner)[0], 200)
            return 'Do not save'

        self.assertEqual(self.work(side_effect=model).call_count, 1)
        self.assertEqual(self.info(owner, file)['state'], 'cancelled')
        self.assertEqual(self.info(owner, file)['ocr_quota']['used'], 0)
        with self.mod.db() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM file_text_chunks WHERE file_id=?', (file['id'],)).fetchone()[0], 0)

    def test_provider_retry_reserves_once_then_refunds_on_terminal_failure(self):
        owner, _ = self.account('ocr-provider')
        file = self.upload(owner)
        job = self.enqueue(owner, file)['job_id']
        for attempt in range(3):
            self.work(side_effect=DomainError(429, 'Busy'))
            self.assertEqual(self.info(owner, file)['ocr_quota']['used'], 1 if attempt < 2 else 0)
            with self.mod.db() as con:
                con.execute('UPDATE assistant_jobs SET next_attempt_at=0 WHERE id=?', (job,))
        self.assertEqual(self.info(owner, file)['state'], 'failed')

    def test_empty_result_and_corrupt_render_refund_without_partial_index(self):
        owner, _ = self.account('ocr-empty')
        file = self.upload(owner)
        self.enqueue(owner, file)
        self.work(text='')
        self.assertEqual(self.info(owner, file)['state'], 'failed')
        self.assertEqual(self.info(owner, file)['ocr_quota']['used'], 0)
        self.enqueue(owner, file, 'again')
        with patch('backend.file_processing.isolated_extract', return_value={'pages': [[3, 'bad']], 'truncated': False, 'total_pages': 1}):
            self.work().assert_not_called()
        self.assertEqual(self.info(owner, file)['ocr_quota']['used'], 0)

    def test_source_change_logout_and_lost_lease_never_publish_text(self):
        for case in ('source', 'logout', 'lease'):
            owner, _ = self.account('ocr-fence-' + case)
            file = self.upload(owner)
            job = self.enqueue(owner, file)['job_id']

            def model(_image):
                if case == 'logout':
                    self.call('/auth/logout', 'POST', {}, owner)
                else:
                    with self.mod.db() as con:
                        con.execute('UPDATE files SET sha256=? WHERE id=?' if case == 'source' else 'UPDATE assistant_jobs SET lease_token=? WHERE id=?', ('changed', file['id'] if case == 'source' else job))
                return 'Stale text'

            self.work(side_effect=model)
            with self.mod.db() as con:
                self.assertEqual(con.execute('SELECT count(*) FROM file_text_chunks WHERE file_id=?', (file['id'],)).fetchone()[0], 0)
                self.assertEqual(con.execute('SELECT result FROM assistant_jobs WHERE id=?', (job,)).fetchone()[0], '{}')

    def test_monthly_quota_is_three_and_chat_quota_stays_zero(self):
        owner, _ = self.account('ocr-month')
        for number in range(3):
            file = self.upload(owner)
            self.enqueue(owner, file, str(number))
            self.work()
        file = self.upload(owner)
        self.assertEqual(self.call('/files/' + file['id'] + '/ocr', 'POST', {}, owner, key='fourth')[0], 429)
        self.assertEqual(self.info(owner, file)['ocr_quota']['used'], 3)
        self.assertEqual(self.call('/assistant', token=owner)[1]['quota']['used'], 0)

    def test_mixed_pdf_preserves_text_and_only_recognizes_missing_page(self):
        owner, _ = self.account('ocr-mixed')
        file = self.upload(owner, 4, text_pages=(1, 3, 4))
        self.assertEqual(self.info(owner, file)['missing_text_pages'], [2])
        self.enqueue(owner, file)
        self.assertEqual(self.work().call_count, 1)
        info = self.info(owner, file)
        self.assertEqual(info['state'], 'ready')
        self.assertEqual(info['pages'], 4)
        self.assertFalse(info['truncated'])
        self.assertEqual(info['missing_text_pages'], [])
        with self.mod.db() as con:
            chunks = con.execute('SELECT page,text FROM file_text_chunks WHERE file_id=? ORDER BY page', (file['id'],)).fetchall()
            self.assertEqual([row['page'] for row in chunks], [1, 2, 3, 4])
            for row in chunks:
                self.assertIn('9876.54' if row['page'] != 2 else '1234.50', row['text'])

    def test_mixed_pdf_later_scans_are_explicitly_partial_without_useless_ocr(self):
        owner, _ = self.account('ocr-later-scan')
        file = self.upload(owner, 4, text_pages=(1, 2, 4), expected='ready')
        info = self.info(owner, file)
        self.assertTrue(info['truncated'])
        self.assertEqual(info['missing_text_pages'], [3])
        self.assertFalse(info['ocr_supported'])
        self.assertEqual(self.call('/files/' + file['id'] + '/ocr', 'POST', {}, owner, key='later')[0], 409)

    def test_mixed_pdf_partial_failure_retains_original_text_and_refunds(self):
        owner, _ = self.account('ocr-mixed-failure')
        file = self.upload(owner, 3, text_pages=(1, 3))
        self.enqueue(owner, file)
        self.work(text='')
        info = self.info(owner, file)
        self.assertEqual(info['state'], 'failed')
        self.assertEqual(info['ocr_quota']['used'], 0)
        with self.mod.db() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM file_text_chunks WHERE file_id=?', (file['id'],)).fetchone()[0], 2)
        self.enqueue(owner, file, 'retry-mixed')
        self.assertEqual(self.work().call_count, 1)
        self.assertFalse(self.info(owner, file)['truncated'])
