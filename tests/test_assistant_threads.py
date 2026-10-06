import concurrent.futures
import base64
import os
import unittest
from unittest.mock import patch

from tests import test_business


class AssistantThreadTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def create(self, owner, **fields):
        status, result = self.call('/assistant/conversations', 'POST', {'title': 'Рабочий диалог', **fields}, owner)
        self.assertEqual(status, 201, result)
        return result['conversation']

    def ask(self, owner, thread, **fields):
        with patch.dict(os.environ, OPENROUTER_API_KEY='test-not-real'), patch(
            'backend.assistant.query_model', return_value={'content': 'Проверено'},
        ) as provider:
            status, result = self.call('/assistant/chat', 'POST',
                                       {'text': 'Расскажи об этой записи', 'conversation_id': thread['id'], **fields}, owner)
        return status, result, provider

    def test_stored_context_is_verified_and_does_not_mix_history(self):
        owner, _ = self.account('thread-context')
        quote = self.call('/quotes', 'POST', {'title': 'Ремонт', 'client': 'Клиент', 'amount': 10000}, owner)[1]['quote']
        thread = self.create(owner, context_entity='quotes', context_id=' '+quote['id']+' ')
        self.assertEqual(thread['context_id'],quote['id'])
        status, _, provider = self.ask(owner, thread)
        self.assertEqual(status, 200)
        self.assertIn(quote['id'], provider.call_args.args[0][0]['content'])
        self.assertEqual(self.call('/assistant', token=owner)[1]['messages'], [])
        messages = self.call('/assistant/conversations/'+thread['id'], token=owner)[1]['messages']
        self.assertEqual(len(messages), 2)
        other = self.create(owner)
        status, _, provider = self.ask(owner, other)
        self.assertEqual(status, 200)
        self.assertNotIn(quote['id'], provider.call_args.args[0][0]['content'])
        self.assertNotIn('Проверено', [m['content'] for m in provider.call_args.args[0]])

    def test_clear_and_explicit_null_do_not_restore_context(self):
        owner, _ = self.account('thread-clear')
        client = self.call('/clients', 'POST', {'name': 'Клиент'}, owner)[1]['item']
        thread = self.create(owner, context_entity='clients', context_id=client['id'])
        status, _, provider = self.ask(owner, thread, context=None)
        self.assertEqual(status, 200)
        self.assertNotIn(client['id'], provider.call_args.args[0][0]['content'])
        status, result = self.call('/assistant/conversations/'+thread['id'], 'PATCH',
                                   {'context_entity': '', 'context_id': ''}, owner)
        self.assertEqual(status, 200, result)
        self.assertEqual(result['conversation']['context_id'], '')
        status, _, provider = self.ask(owner, thread)
        self.assertEqual(status, 200)
        self.assertNotIn(client['id'], provider.call_args.args[0][0]['content'])

    def test_foreign_and_malformed_context_rejected_before_provider(self):
        owner, _ = self.account('thread-owner')
        stranger, _ = self.account('thread-foreign')
        client = self.call('/clients', 'POST', {'name': 'Чужой'}, stranger)[1]['item']
        for fields in ({'context_id': client['id']}, {'context_entity': 'clients'},
                       {'context_entity': 3, 'context_id': client['id']},
                       {'context_entity': 'users', 'context_id': client['id']}):
            self.assertEqual(self.call('/assistant/conversations','POST',{'title':'Нельзя',**fields},owner)[0],400)
        self.assertEqual(self.call('/assistant/conversations','POST',
                                   {'title':'Нельзя','context_entity':'clients','context_id':client['id']},owner)[0],404)
        thread = self.create(owner)
        self.assertEqual(self.call('/assistant/conversations/'+thread['id'],'PATCH',
                                   {'context_entity':'clients','context_id':client['id']},owner)[0],404)
        self.assertEqual(self.call('/assistant/conversations/'+thread['id'],'PATCH',
                                   {'context_entity':'','context_id':''},stranger)[0],404)
        status, _, provider = self.ask(stranger, thread)
        self.assertEqual(status,404)
        provider.assert_not_called()

    def test_deleted_source_can_be_cleared_without_spending_quota(self):
        owner, _ = self.account('thread-deleted')
        client = self.call('/clients','POST',{'name':'Удаляемый'},owner)[1]['item']
        thread = self.create(owner,context_entity='clients',context_id=client['id'])
        self.assertEqual(self.call('/clients/'+client['id'],'DELETE',token=owner)[0],200)
        remaining = self.call('/assistant',token=owner)[1]['quota']['remaining']
        status, _, provider = self.ask(owner,thread)
        self.assertEqual(status,404)
        provider.assert_not_called()
        self.assertEqual(self.call('/assistant',token=owner)[1]['quota']['remaining'],remaining)
        self.assertEqual(self.call('/assistant/conversations/'+thread['id'],'PATCH',{'title':'Без записи'},owner)[0],200)
        self.assertEqual(self.call('/assistant/conversations/'+thread['id'],'PATCH',
                                   {'context_entity':'','context_id':''},owner)[0],200)

    def test_create_cap_holds_under_concurrent_requests_and_fork(self):
        owner, _ = self.account('thread-cap')
        first = self.create(owner)
        self.assertEqual(self.ask(owner,first)[0],200)
        for _ in range(48):
            self.create(owner)
        messages = self.call('/assistant/conversations/'+first['id'],token=owner)[1]['messages']
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda i:self.call('/assistant/conversations','POST',{'title':str(i)},owner)[0],range(4)))
        self.assertEqual(sorted(results),[201,409,409,409])
        self.assertEqual(len(self.call('/assistant/conversations',token=owner)[1]['items']),50)
        self.assertEqual(self.call('/assistant/conversations/'+first['id']+'/fork','POST',
                                   {'message_id':messages[-1]['id']},owner)[0],409)
        self.assertEqual(self.call('/assistant/conversations/'+first['id'],'DELETE',token=owner)[0],200)
        self.create(owner)

    def test_concurrent_pin_does_not_restore_cleared_context(self):
        owner, _ = self.account('thread-parallel-context')
        client = self.call('/clients','POST',{'name':'Клиент'},owner)[1]['item']
        thread = self.create(owner)
        path = '/assistant/conversations/'+thread['id']
        for _ in range(5):
            self.assertEqual(self.call(path,'PATCH',{'pinned':0,'context_entity':'clients','context_id':client['id']},owner)[0],200)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(self.call,path,'PATCH',body,owner)
                        for body in ({'context_entity':'','context_id':''},{'pinned':1})]
                self.assertEqual([job.result()[0] for job in jobs],[200,200])
            result = self.call(path,token=owner)[1]['conversation']
            self.assertEqual(result['context_id'],'')
            self.assertEqual(result['pinned'],1)

    def test_file_context_uses_scoped_metadata_without_payload(self):
        owner, _ = self.account('thread-file')
        stranger, _ = self.account('thread-file-stranger')
        status,result = self.call('/files','POST',{'assistant_upload':True,'name':'brief.txt',
                    'content':base64.b64encode('Рабочий документ'.encode()).decode()},owner)
        self.assertEqual(status,201,result)
        file = result['file']
        status,result = self.call('/files/'+file['id']+'/metadata',token=owner)
        self.assertEqual(status,200,result)
        self.assertEqual(result['file']['name'],'brief.txt')
        self.assertEqual(set(result['file']),{'id','name','mime','size','sha256','created_at','public',
                                             'metadata_etag','client_id','project_id','quote_id','construction_id'})
        self.assertNotIn('Рабочий документ',str(result))
        self.assertEqual(self.call('/files/'+file['id']+'/metadata',token=stranger)[0],404)
        thread = self.create(owner,context_entity='files',context_id=file['id'])
        self.assertEqual(thread['context_id'],file['id'])

    def test_adopt_general_preserves_history_and_replays_without_duplicates(self):
        owner, _ = self.account('general-adopt')
        stranger, _ = self.account('general-stranger')
        with patch.dict(os.environ, OPENROUTER_API_KEY='test-only'), patch('backend.assistant.query_model', return_value={'content': 'Ответ общего диалога'}):
            for token in (owner, stranger):
                self.assertEqual(self.call('/assistant/chat', 'POST', {'text': 'Вопрос общего диалога'}, token)[0], 200)
        original = self.call('/assistant', token=owner)[1]['messages']
        payload = {'title': 'Моя смета', 'adopt_general': True}
        status, result = self.call('/assistant/conversations', 'POST', payload, owner, key='save-general')
        self.assertEqual(status, 201, result)
        thread_id = result['conversation']['id']
        adopted = self.call('/assistant/conversations/'+thread_id, token=owner)[1]['messages']
        self.assertEqual([(m['role'], m['content']) for m in adopted], [(m['role'], m['content']) for m in original])
        self.assertEqual(self.call('/assistant', token=owner)[1]['messages'], [])
        self.assertEqual(len(self.call('/assistant', token=stranger)[1]['messages']), 2)
        status, replay = self.call('/assistant/conversations', 'POST', payload, owner, key='save-general')
        self.assertEqual(status, 200, replay)
        self.assertEqual(replay['conversation']['id'], thread_id)
        self.assertEqual(len(self.call('/assistant/conversations', token=owner)[1]['items']), 1)
        self.assertEqual(self.call('/assistant/conversations', 'POST', {'adopt_general': 'yes'}, owner)[0], 400)

    def test_clear_general_keeps_named_and_other_users_history(self):
        owner, _ = self.account('general-clear')
        stranger, _ = self.account('general-keep')
        named = self.create(owner)
        self.assertEqual(self.ask(owner, named)[0], 200)
        with patch.dict(os.environ, OPENROUTER_API_KEY='test-only'), patch('backend.assistant.query_model', return_value={'content': 'Общий ответ'}):
            for token in (owner, stranger):
                self.assertEqual(self.call('/assistant/chat', 'POST', {'text': 'Вопрос'}, token)[0], 200)
        self.assertEqual(self.call('/assistant/conversations/general', 'DELETE', token=owner)[0], 200)
        self.assertEqual(self.call('/assistant', token=owner)[1]['messages'], [])
        self.assertEqual(len(self.call('/assistant/conversations/'+named['id'], token=owner)[1]['messages']), 2)
        self.assertEqual(len(self.call('/assistant', token=stranger)[1]['messages']), 2)

    def test_general_changes_cannot_race_active_stream_or_background_job(self):
        owner, _ = self.account('general-busy')
        with patch('backend.redis_infra.acquire_lock', return_value=None):
            self.assertEqual(self.call('/assistant/conversations', 'POST', {'adopt_general': True}, owner)[0], 409)
            self.assertEqual(self.call('/assistant/conversations/general', 'DELETE', token=owner)[0], 409)
        with patch.dict(os.environ, ASSISTANT_WORKER_SECRET='isolated-worker-secret-0123456789', OPENROUTER_API_KEY='test-only'):
            self.assertEqual(self.call('/assistant/jobs', 'POST', {'text': 'Фоновая задача'}, owner, key='general-job')[0], 202)
            self.assertEqual(self.call('/assistant/conversations', 'POST', {'adopt_general': True}, owner)[0], 409)
            self.assertEqual(self.call('/assistant/conversations/general', 'DELETE', token=owner)[0], 409)
