"""Checkout failures reproduced without sending requests to a payment provider."""

import concurrent.futures
import hashlib
import json
import os
import secrets
import threading
import urllib.error
import urllib.request
import unittest
from unittest.mock import patch

from tests import test_flows


class CheckoutRegressions(unittest.TestCase):
    setUpClass = classmethod(test_flows.FlowTests.setUpClass.__func__)
    tearDownClass = classmethod(test_flows.FlowTests.tearDownClass.__func__)

    def account(self):
        token, user_id = secrets.token_urlsafe(32), self.mod.uid()
        with self.mod.db() as con:
            con.execute("INSERT INTO users(id,email,password_hash,name,created_at,email_verified_at) VALUES(?,?,?,'QA',?,?)",
                        (user_id, user_id+'@test.invalid', 'unused', self.mod.now(), self.mod.now()))
            con.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)",
                        (self.mod.uid(), user_id, hashlib.sha256(token.encode()).hexdigest(), self.mod.now()+3600))
        return token, user_id

    def checkout(self, token, key, plan='pro_month'):
        req = urllib.request.Request(self.base+'/api/billing/checkout', json.dumps({'plan': plan}).encode(),
                {'Authorization': 'Bearer '+token, 'Content-Type': 'application/json', 'Idempotency-Key': key})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            return response.code, json.load(response)

    @staticmethod
    def payment(payload, key):
        return {'id': 'provider-'+key, 'test': False, 'recipient': {'account_id': 'qa-shop'},
                'amount': payload['amount'], 'metadata': payload['metadata'],
                'confirmation': {'confirmation_url': 'https://pay.example.test/'+key}}

    def env(self):
        return patch.dict(os.environ, YOOKASSA_MODE='live', YOOKASSA_SHOP_ID='qa-shop',
                          YOOKASSA_SECRET_KEY='qa-not-a-real-key', YOOKASSA_MERCHANT_TYPE='self_employed')

    def test_invalid_plan_types_are_client_errors_without_provider_calls(self):
        token, _ = self.account()
        with self.env(), patch.object(self.mod.Handler, 'provider_call') as provider:
            for plan in ([], {}, None, True):
                self.assertEqual(self.checkout(token, 'invalid-plan-key-0001', plan)[0], 400)
            provider.assert_not_called()

    def test_provider_keys_are_bounded_and_account_scoped(self):
        accounts = [self.account(), self.account()]
        keys = []

        def provider(handler, path, method, payload, key):
            keys.append(key)
            return self.payment(payload, key)

        with self.env(), patch.object(self.mod.Handler, 'provider_call', provider):
            for token, _ in accounts:
                self.assertEqual(self.checkout(token, 'a'*100)[0], 201)
        self.assertEqual(len(set(keys)), 2)
        self.assertTrue(all(len(key) <= 64 and key.isascii() for key in keys))

    def test_concurrent_same_checkout_is_replayed_instead_of_conflict(self):
        token, user_id = self.account()
        barrier = threading.Barrier(2)

        def provider(handler, path, method, payload, key):
            barrier.wait(timeout=5)
            return self.payment(payload, key)

        with self.env(), patch.object(self.mod.Handler, 'provider_call', provider):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.checkout(token, 'concurrent-checkout-0001'), range(2)))
        self.assertEqual(sorted(code for code, _ in results), [200, 201], results)
        self.assertEqual(results[0][1]['url'], results[1][1]['url'])
        with self.mod.db() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM payments WHERE user_id=?', (user_id,)).fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT count(*) FROM events WHERE user_id=? AND name='checkout_started'", (user_id,)).fetchone()[0], 1)
            self.assertEqual(con.execute('SELECT plan FROM users WHERE id=?', (user_id,)).fetchone()[0], 'free')

    def test_wrong_payment_owner_is_not_persisted(self):
        token, user_id = self.account()

        def provider(handler, path, method, payload, key):
            result = self.payment(payload, key)
            result['metadata'] = {'user_id': 'another-user', 'plan': 'pro_month'}
            return result

        with self.env(), patch.object(self.mod.Handler, 'provider_call', provider):
            self.assertEqual(self.checkout(token, 'wrong-owner-checkout-1')[0], 502)
        with self.mod.db() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM payments WHERE user_id=?', (user_id,)).fetchone()[0], 0)
