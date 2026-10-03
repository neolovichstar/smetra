"""Receipt drafts persist without holding a write lock during model calls."""

import base64
import concurrent.futures
import io
import os
import unittest
from unittest.mock import patch

from PIL import Image
import test_business
from test_assistant_jobs import SECRET, worker_token
from backend.business import DomainError


class ReceiptJobTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def setUp(self):
        test_business.BusinessFlows.setUp(self)
        env = patch.dict(os.environ, ASSISTANT_WORKER_SECRET=SECRET, OPENROUTER_API_KEY='test-only', OPENROUTER_OCR_MODEL='openrouter/free')
        env.start()
        self.addCleanup(env.stop)
        with self.mod.db() as con:
            con.execute('DELETE FROM assistant_jobs')

    def receipt(self, owner, obj=None):
        obj = obj or self.call('/construction/objects', 'POST', {'name': 'Receipt QA'}, owner)[1]['object']['id']
        image = io.BytesIO()
        Image.new('RGB', (30, 30), 'white').save(image, format='PNG')
        file = self.call('/files', 'POST', {'construction_id': obj, 'name': 'receipt.png', 'content': base64.b64encode(image.getvalue()).decode()}, owner)[1]['file']
        return obj, file['id'], f"/construction/objects/{obj}/receipt-ocr/{file['id']}"

    def enqueue(self, owner, path, key='receipt'):
        code, body = self.call(path, 'POST', {}, owner, key=key)
        self.assertIn(code, (200, 202), body)
        return body

    def work(self, side_effect=None):
        with patch('backend.receipt_ocr._request', return_value={'merchant': 'Store', 'amount_kopecks': 123450, 'date': '2026-10-03'}, side_effect=side_effect) as model:
            code, body = self.call('/cron/assistant', token=worker_token())
        self.assertEqual(code, 200, body)
        return model

    def test_result_survives_navigation_is_replayed_without_new_quota_and_never_writes_purchase(self):
        owner, _ = self.account('receipt-ready')
        obj, _, path = self.receipt(owner)
        with patch('backend.receipt_ocr._request') as model:
            pending = self.enqueue(owner, path)
        model.assert_not_called()
        self.assertEqual(pending['state'], 'queued')
        self.assertEqual(pending['quota']['used'], 1)
        self.work().assert_called_once()
        result = self.call(path, token=owner)[1]
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['draft']['amount_kopecks'], 123450)
        self.assertTrue(result['needs_confirmation'])
        self.assertEqual(self.enqueue(owner, path, 'another')['quota']['used'], 1)
        self.assertEqual(self.call(f'/construction/objects/{obj}', token=owner)[1]['purchases'], [])
        self.assertEqual(self.call('/assistant', token=owner)[1]['quota']['used'], 0)
        self.assertEqual(self.call('/assistant/jobs', token=owner)[1]['jobs'], [])
        self.assertNotIn('session_hash', str(result))

    def test_lost_response_and_concurrent_enqueue_charge_once(self):
        owner, _ = self.account('receipt-parallel')
        _, _, path = self.receipt(owner)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.call(path, 'POST', {}, owner, key='same'), range(4)))
        self.assertTrue(all(code in (200, 202) for code, _ in responses), responses)
        self.assertEqual(len({body['job_id'] for _, body in responses}), 1)
        self.assertEqual(self.call(path, token=owner)[1]['quota']['used'], 1)
        _, _, other = self.receipt(owner)
        self.assertEqual(self.call(other, 'POST', {}, owner, key='same')[0], 409)

    def test_private_access_wrong_object_and_paid_model_rejected(self):
        owner, _ = self.account('receipt-private')
        outsider, _ = self.account('receipt-outsider')
        _, file, path = self.receipt(owner)
        for method in ('GET', 'POST', 'DELETE'):
            self.assertEqual(self.call(path, method, {} if method == 'POST' else None, outsider, key='private')[0], 404)
        other = self.call('/construction/objects', 'POST', {'name': 'Other'}, owner)[1]['object']['id']
        self.assertEqual(self.call(f'/construction/objects/{other}/receipt-ocr/{file}', 'POST', {}, owner, key='wrong')[0], 400)
        with patch.dict(os.environ, OPENROUTER_OCR_MODEL='paid/model'):
            self.assertEqual(self.call(path, 'POST', {}, owner, key='paid')[0], 503)
        self.assertEqual(self.call(path, token=owner)[1]['quota']['used'], 0)

    def test_queued_cancel_and_delete_refund_once_without_model_call(self):
        owner, _ = self.account('receipt-cancel')
        _, file, path = self.receipt(owner)
        self.enqueue(owner, path)
        for _ in range(2):
            self.assertEqual(self.call(path, 'DELETE', token=owner)[1]['quota']['used'], 0)
        self.work().assert_not_called()
        self.enqueue(owner, path, 'retry')
        self.assertEqual(self.call('/files/' + file, 'DELETE', token=owner)[0], 200)
        with self.mod.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM assistant_jobs WHERE file_id=?", (file,)).fetchone()[0], 0)
        self.work().assert_not_called()

    def test_inflight_cancel_does_not_hold_database_lock_or_publish_draft(self):
        owner, _ = self.account('receipt-inflight')
        obj, _, path = self.receipt(owner)
        self.enqueue(owner, path)

        def model(*_):
            code, _ = self.call(f'/construction/objects/{obj}', 'PATCH', {'name': 'Still responsive'}, owner)
            self.assertEqual(code, 200)
            self.assertEqual(self.call(path, 'DELETE', token=owner)[0], 200)
            return {'merchant': 'Store', 'amount_kopecks': 99900, 'date': ''}

        self.work(model)
        info = self.call(path, token=owner)[1]
        self.assertEqual(info['state'], 'cancelled')
        self.assertEqual(info['quota']['used'], 0)
        self.assertNotIn('draft', info)

    def test_provider_retry_uses_one_reservation_and_terminal_error_refunds(self):
        owner, _ = self.account('receipt-retry')
        _, _, path = self.receipt(owner)
        pending = self.enqueue(owner, path)
        for attempt in range(3):
            self.work(DomainError(429, 'Busy'))
            info = self.call(path, token=owner)[1]
            self.assertEqual(info['quota']['used'], 1 if attempt < 2 else 0)
            with self.mod.db() as con:
                con.execute('UPDATE assistant_jobs SET next_attempt_at=0 WHERE id=?', (pending['job_id'],))
        self.assertEqual(info['state'], 'failed')
        self.enqueue(owner, path, 'manual-retry')
        self.work()
        self.assertEqual(self.call(path, token=owner)[1]['state'], 'completed')

    def test_three_receipts_per_month_and_active_cap(self):
        owner, _ = self.account('receipt-quota')
        receipts = [self.receipt(owner) for _ in range(4)]
        self.enqueue(owner, receipts[0][2], 'first')
        self.enqueue(owner, receipts[1][2], 'second')
        self.assertEqual(self.call(receipts[2][2], 'POST', {}, owner, key='third')[0], 429)
        self.work()
        self.work()
        self.enqueue(owner, receipts[2][2], 'third')
        self.work()
        self.assertEqual(self.call(receipts[3][2], 'POST', {}, owner, key='fourth')[0], 429)
        self.assertEqual(self.call(receipts[0][2], token=owner)[1]['quota']['used'], 3)

    def test_logout_during_model_call_invalidates_result(self):
        owner, _ = self.account('receipt-logout')
        _, _, path = self.receipt(owner)
        pending = self.enqueue(owner, path)

        def model(*_):
            self.call('/auth/logout', 'POST', {}, owner)
            return {'merchant': 'Store', 'amount_kopecks': 100, 'date': ''}

        self.work(model)
        with self.mod.db() as con:
            row = con.execute('SELECT * FROM assistant_jobs WHERE id=?', (pending['job_id'],)).fetchone()
            self.assertEqual(row['status'], 'failed')
            self.assertEqual(row['result'], '{}')
            self.assertEqual(row['quota_refunded'], 1)

    def test_source_change_and_invalid_model_total_do_not_publish_or_charge(self):
        for label, mutate in [('changed', True), ('invalid', False)]:
            owner, _ = self.account('receipt-' + label)
            _, file, path = self.receipt(owner)
            pending = self.enqueue(owner, path)

            def model(*_):
                if mutate:
                    with self.mod.db() as con:
                        con.execute('UPDATE files SET sha256=? WHERE id=?', ('changed-source', file))
                return {'merchant': 'Store', 'amount_kopecks': 123450 if mutate else True, 'date': ''}

            self.work(model)
            with self.mod.db() as con:
                row = con.execute('SELECT * FROM assistant_jobs WHERE id=?', (pending['job_id'],)).fetchone()
                self.assertEqual(row['result'], '{}')
                self.assertEqual(row['quota_refunded'], 1)
                self.assertEqual(row['status'], 'failed')

    def test_old_request_key_replays_original_cancelled_job_after_manual_retry(self):
        owner, _ = self.account('receipt-original')
        _, _, path = self.receipt(owner)
        original = self.enqueue(owner, path)
        self.call(path, 'DELETE', token=owner)
        replacement = self.enqueue(owner, path, 'replacement')
        replay = self.enqueue(owner, path)
        self.assertEqual(replay['job_id'], original['job_id'])
        self.assertEqual(replay['state'], 'cancelled')
        self.assertNotEqual(replacement['job_id'], original['job_id'])
        self.assertEqual(replay['quota']['used'], 1)

    def test_lost_lease_does_not_publish_result(self):
        owner, _ = self.account('receipt-lease')
        _, _, path = self.receipt(owner)
        pending = self.enqueue(owner, path)

        def model(*_):
            with self.mod.db() as con:
                con.execute('UPDATE assistant_jobs SET lease_token=? WHERE id=?', ('another-worker', pending['job_id']))
            return {'merchant': 'Store', 'amount_kopecks': 100, 'date': ''}

        self.work(model)
        with self.mod.db() as con:
            row = con.execute('SELECT * FROM assistant_jobs WHERE id=?', (pending['job_id'],)).fetchone()
            self.assertEqual(row['lease_token'], 'another-worker')
            self.assertEqual(row['result'], '{}')
