import concurrent.futures
import json
import hashlib
import hmac
import os
import time
import unittest
import uuid
from unittest.mock import patch

from backend.business import DomainError
from tests import test_business

SECRET = 'isolated-worker-test-secret-0123456789'


def worker_token(moment=None, nonce=None):
    moment, nonce = str(int(time.time()) if moment is None else moment), nonce or uuid.uuid4().hex
    signature = hmac.new(SECRET.encode(), ('smetra-assistant-worker:v1:' + moment + ':' + nonce).encode(), hashlib.sha256).hexdigest()
    return f'v1.{moment}.{nonce}.{signature}'


class AssistantJobTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def setUp(self):
        test_business.BusinessFlows.setUp(self)
        env = patch.dict(os.environ, ASSISTANT_WORKER_SECRET=SECRET, OPENROUTER_API_KEY='test-only')
        env.start()
        self.addCleanup(env.stop)

    def enqueue(self, owner, key='one', **fields):
        code, result = self.call('/assistant/jobs', 'POST', {'text': 'Проверь данные', **fields}, owner, key=key)
        self.assertIn(code, (200, 202), result)
        return result['job']

    def run_job(self, response=None, side_effect=None):
        with patch('backend.assistant.query_model', return_value=response or {'content': 'Готовый ответ'}, side_effect=side_effect) as model:
            code, result = self.call('/cron/assistant', token=worker_token())
        self.assertEqual(code, 200, result)
        return model

    def due(self, job):
        with self.mod.db() as con:
            con.execute('UPDATE assistant_jobs SET next_attempt_at=0,lease_until=0 WHERE id=?', (job['id'],))

    def test_first_message_creates_durable_named_conversation_without_empty_default(self):
        owner, _ = self.account('job-auto-thread')
        self.assertEqual(self.call('/assistant/conversations', token=owner)[1]['items'], [])
        job = self.enqueue(owner, key='first-written-message')
        thread_id = job['conversation_id']
        self.assertTrue(thread_id)
        items = self.call('/assistant/conversations', token=owner)[1]['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], thread_id)
        self.assertEqual(items[0]['title'], 'Новый диалог')
        with patch('backend.chat_titles.generate_title', return_value='Проверка закупок'):
            self.run_job()
        saved = self.call('/assistant/conversations/'+thread_id, token=owner)[1]
        self.assertEqual([m['role'] for m in saved['messages']], ['user', 'assistant'])
        self.assertEqual(self.call('/assistant/conversations', token=owner)[1]['items'][0]['title'], 'Проверка закупок')
        self.assertEqual(self.call('/assistant', token=owner)[1]['messages'], [])

    def test_legacy_anonymous_history_is_archived_on_first_new_message(self):
        owner, _ = self.account('job-legacy-archive')
        with patch('backend.assistant.query_model', return_value={'content':'Старый ответ'}):
            self.assertEqual(self.call('/assistant/chat', 'POST', {'text':'Старый вопрос'}, owner)[0], 200)
        job = self.enqueue(owner, key='new-post-legacy')
        items = self.call('/assistant/conversations', token=owner)[1]['items']
        self.assertEqual({x['title'] for x in items}, {'История прежнего чата', 'Новый диалог'})
        previous = next(x for x in items if x['title'] == 'История прежнего чата')
        history = self.call('/assistant/conversations/'+previous['id'], token=owner)[1]['messages']
        self.assertEqual([x['content'] for x in history], ['Старый вопрос', 'Старый ответ'])
        self.assertNotEqual(job['conversation_id'], previous['id'])
        self.assertEqual(self.call('/assistant', token=owner)[1]['messages'], [])
        # Do not leave a queued job for later worker tests to claim by age.
        self.assertEqual(self.call('/assistant/jobs/'+job['id'], 'DELETE', token=owner)[0], 200)

    def test_creation_replay_is_atomic_and_private(self):
        owner, _ = self.account('job-replay')
        stranger, _ = self.account('job-stranger')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.enqueue(owner), range(2)))
        self.assertEqual(results[0]['id'], results[1]['id'])
        # Tokens are charged for finished answers only; a queued job costs nothing yet.
        self.assertEqual(self.call('/assistant', token=owner)[1]['quota']['used'], 0)
        self.assertNotIn('session_hash', str(results))
        self.assertNotIn('quota_key', str(results))
        self.assertEqual(self.call('/assistant/jobs/'+results[0]['id'], token=stranger)[0], 404)
        self.assertEqual(self.call('/assistant/jobs/'+results[0]['id'], 'DELETE', token=stranger)[0], 404)
        self.assertEqual(self.call('/assistant/jobs', token=stranger)[1]['jobs'], [])
        self.assertEqual(self.call('/assistant/jobs','POST',{'text':'Другой запрос'},owner,key='one')[0],409)
        self.call('/assistant/jobs/'+results[0]['id'],'DELETE',token=owner)

    def test_idempotent_chat_retry_does_not_use_new_rate_limit_credit(self):
        from backend.app import Handler

        owner, _ = self.account('job-duplicate-throttle')
        recorded = []
        original = Handler.throttle

        def observe(handler, key, limit=15, window=60):
            if key.startswith('assistant:'):
                recorded.append(key)
            return original(handler, key, limit, window)

        with patch.object(Handler, 'throttle', observe):
            first = self.enqueue(owner, key='same-message-retry')
            for _ in range(3):
                again = self.enqueue(owner, key='same-message-retry')
                self.assertEqual(first['id'], again['id'])
        self.assertEqual(len(recorded), 1)
        self.call('/assistant/jobs/' + first['id'], 'DELETE', token=owner)

    def test_completion_survives_screen_exit_and_is_not_run_twice(self):
        owner, _ = self.account('job-complete')
        thread = self.call('/assistant/conversations','POST',{'title':'Проверка'},owner)[1]['conversation']
        job = self.enqueue(owner,conversation_id=thread['id'])
        self.run_job()
        result = self.call('/assistant/jobs/'+job['id'],token=owner)[1]['job']
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['result']['answer'],'Готовый ответ')
        history = self.call('/assistant/conversations/'+thread['id'],token=owner)[1]['messages']
        self.assertEqual(len(history),2)
        self.run_job().assert_not_called()
        self.assertGreater(self.call('/assistant',token=owner)[1]['quota']['used'],0)

    def test_queued_cancel_refunds_once_and_provider_never_runs(self):
        owner, _ = self.account('job-cancel')
        job = self.enqueue(owner)
        for _ in range(2):
            self.assertEqual(self.call('/assistant/jobs/'+job['id'],'DELETE',token=owner)[1]['job']['status'],'cancelled')
        self.run_job().assert_not_called()
        self.assertEqual(self.call('/assistant',token=owner)[1]['quota']['used'],0)

    def test_cancel_during_generation_does_not_leave_messages_or_proposals(self):
        owner, _ = self.account('job-inflight-cancel')
        job = self.enqueue(owner)

        def model(_messages):
            self.call('/assistant/jobs/'+job['id'],'DELETE',token=owner)
            return {'tool_calls':[{'id':'call1','type':'function','function':{
                'name':'create_clients','arguments':json.dumps({'name':'Не сохранять'})}}]}

        self.run_job(side_effect=model)
        result = self.call('/assistant',token=owner)[1]
        self.assertEqual(result['messages'],[])
        self.assertEqual(result['actions'],[])
        self.assertEqual(result['quota']['used'],0)
        self.assertEqual(self.call('/assistant/jobs/'+job['id'],token=owner)[1]['job']['status'],'cancelled')

    def test_proposal_is_reviewable_and_never_applied_by_worker(self):
        owner, _ = self.account('job-proposal')
        job = self.enqueue(owner)
        self.run_job(response={'tool_calls':[{'id':'call1','type':'function','function':{
            'name':'create_clients','arguments':json.dumps({'name':'Новый клиент'})}}]})
        self.assertEqual(self.call('/clients',token=owner)[1]['items'],[])
        result = self.call('/assistant/jobs/'+job['id'],token=owner)[1]['job']
        self.assertEqual(result['status'],'completed')
        actions = self.call('/assistant',token=owner)[1]['actions']
        self.assertEqual(len(actions),1)
        self.assertEqual(result['result']['actions'][0]['id'],actions[0]['id'])
        self.assertEqual(self.call('/assistant/confirm','POST',{'id':actions[0]['id']},owner)[0],200)
        self.assertEqual(len(self.call('/clients',token=owner)[1]['items']),1)

    def test_cancel_after_proposal_preparation_rolls_back_every_output(self):
        from backend import assistant

        owner, _ = self.account('job-cancel-prepared')
        job = self.enqueue(owner)
        original = assistant.prepare

        def prepare_then_cancel(service, name, args):
            action = original(service, name, args)
            self.assertEqual(len(service.assistant_deferred_actions),1)
            self.call('/assistant/jobs/'+job['id'],'DELETE',token=owner)
            return action

        with patch('backend.assistant.prepare',side_effect=prepare_then_cancel):
            self.run_job(response={'tool_calls':[{'id':'call1','type':'function','function':{
                'name':'create_clients','arguments':json.dumps({'name':'Отменённое предложение'})}}]})
        result = self.call('/assistant',token=owner)[1]
        self.assertEqual(result['messages'],[])
        self.assertEqual(result['actions'],[])
        self.assertEqual(result['quota']['used'],0)

    def test_backoff_exhaustion_and_refund_are_bounded(self):
        owner, _ = self.account('job-retries')
        job = self.enqueue(owner)
        for attempt in range(1,4):
            self.run_job(side_effect=DomainError(502,'Модель недоступна'))
            result = self.call('/assistant/jobs/'+job['id'],token=owner)[1]['job']
            self.assertEqual(result['attempts'],attempt)
            self.assertEqual(result['status'],'retry' if attempt<3 else 'failed')
            if attempt<3:
                self.assertEqual(self.call('/assistant',token=owner)[1]['quota']['used'],0)
                self.run_job().assert_not_called()
                self.due(job)
        self.run_job().assert_not_called()
        self.assertEqual(self.call('/assistant',token=owner)[1]['quota']['used'],0)

    def test_revoked_session_is_not_an_authentication_bypass(self):
        owner, user_id = self.account('job-revoke')
        job = self.enqueue(owner)
        with self.mod.db() as con:
            con.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
        self.run_job().assert_not_called()
        with self.mod.db() as con:
            row = con.execute('SELECT status,quota_refunded FROM assistant_jobs WHERE id=?',(job['id'],)).fetchone()
        self.assertEqual(row['status'],'failed')
        self.assertEqual(row['quota_refunded'],1)

    def test_deleted_context_fails_before_provider_and_refunds(self):
        owner, _ = self.account('job-context')
        client = self.call('/clients','POST',{'name':'Контекст'},owner)[1]['item']
        job = self.enqueue(owner,context={'entity':'clients','id':client['id']})
        self.call('/clients/'+client['id'],'DELETE',token=owner)
        self.run_job().assert_not_called()
        self.assertEqual(self.call('/assistant/jobs/'+job['id'],token=owner)[1]['job']['status'],'failed')
        self.assertEqual(self.call('/assistant',token=owner)[1]['quota']['used'],0)

    def test_lost_lease_cannot_commit_duplicate_result(self):
        owner, _ = self.account('job-lease')
        job = self.enqueue(owner)

        def superseded(_messages):
            from backend.assistant_jobs import claim

            self.due(job)
            with self.mod.db() as con:
                claimed = claim(con)
                self.assertEqual(claimed['attempts'],2)
            return {'content':'Устаревшая попытка'}

        self.run_job(side_effect=superseded)
        self.assertEqual(self.call('/assistant',token=owner)[1]['messages'],[])
        self.due(job)
        self.run_job()
        result = self.call('/assistant/jobs/'+job['id'],token=owner)[1]['job']
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['attempts'],3)
        self.assertEqual(len(self.call('/assistant/conversations/'+job['conversation_id'],token=owner)[1]['messages']),2)

    def test_worker_auth_and_pending_thread_deletion(self):
        owner, _ = self.account('job-worker-auth')
        thread = self.call('/assistant/conversations','POST',{'title':'Не удалять'},owner)[1]['conversation']
        job = self.enqueue(owner,conversation_id=thread['id'])
        with patch('backend.assistant.query_model') as provider:
            self.assertEqual(self.call('/cron/assistant',token=owner)[0],401)
            self.assertEqual(self.call('/cron/assistant')[0],401)
            self.assertEqual(self.call('/cron/assistant','POST',{},SECRET)[0],404)
        provider.assert_not_called()
        self.assertEqual(self.call('/assistant/conversations/'+thread['id'],'DELETE',token=owner)[0],409)
        self.call('/assistant/jobs/'+job['id'],'DELETE',token=owner)
        self.assertEqual(self.call('/assistant/conversations/'+thread['id'],'DELETE',token=owner)[0],200)

    def test_worker_signature_is_short_lived_scoped_and_one_time(self):
        owner, _ = self.account('job-signatures')
        job = self.enqueue(owner)
        now = int(time.time())
        # Freeze the verification clock: HTTP scheduling may cross a second and
        # legitimately move a +31s token into the allowed +30s window.
        with patch('backend.assistant_jobs.stamp', return_value=now):
            for token in (SECRET,worker_token(now-121),worker_token(now+31),worker_token(now)[:-1]+'x'):
                self.assertEqual(self.call('/cron/assistant',token=token)[0],401)
        signed = worker_token()
        with patch('backend.assistant.query_model',return_value={'content':'Signed answer'}) as provider:
            self.assertEqual(self.call('/cron/assistant',token=signed)[0],200)
            self.assertEqual(self.call('/cron/assistant',token=signed)[0],429)
        provider.assert_called_once()
        self.assertEqual(self.call('/assistant/jobs/'+job['id'],token=owner)[1]['job']['status'],'completed')


if __name__ == '__main__':
    unittest.main()
