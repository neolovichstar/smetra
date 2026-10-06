import os
import unittest
from unittest.mock import patch

from tests import test_business


class ProfileMemoryTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_profile_is_optional_private_validated_and_updates_display_name(self):
        owner, _ = self.account('profile-owner')
        other, _ = self.account('profile-other')
        fields = {'first_name': 'Анна', 'last_name': 'Смирнова', 'profession': 'Архитектор',
                  'about': 'Делаю проекты квартир', 'company': 'Моя студия'}
        self.assertEqual(self.call('/profile', 'PATCH', fields, owner)[0], 200)
        profile = self.call('/profile', token=owner)[1]['profile']
        for key, value in fields.items():
            self.assertEqual(profile[key], value)
        self.assertEqual(self.call('/me', token=owner)[1]['user']['name'], 'Анна Смирнова')
        self.assertEqual(self.call('/profile', token=other)[1]['profile']['about'], '')
        for invalid in ({'role': 'admin'}, {'about': 'a'*2001}, {'memory_enabled': 5}, {'response_style': 'anything'}):
            self.assertEqual(self.call('/profile', 'PATCH', invalid, owner)[0], 400)
        self.assertEqual(self.call('/profile')[0], 401)

    def test_personal_memory_crud_is_private_and_disabled_entries_are_not_context(self):
        owner, _ = self.account('memory-owner')
        other, _ = self.account('memory-other')
        status, value = self.call('/assistant/memory', 'POST', {'title': 'Работа', 'content': 'Моя специализация — ремонт', 'enabled': 0}, owner)
        self.assertEqual(status, 201, value)
        item_id = value['id']
        self.assertEqual(self.call('/assistant/memory', token=other)[1]['items'], [])
        self.assertEqual(self.call('/assistant/memory/'+item_id, 'DELETE', token=other)[0], 404)
        self.assertEqual(self.call('/assistant/memory/'+item_id, 'PATCH', {'content': 'Чужая правка'}, other)[0], 404)
        self.assertEqual(self.call('/assistant/memory/'+item_id, 'PATCH', {'enabled': 1, 'content': 'Ремонт квартир'}, owner)[0], 200)
        with patch.dict(os.environ, OPENROUTER_API_KEY='test-only'), patch('backend.assistant.query_model', return_value={'content': 'Ответ'}) as provider:
            self.assertEqual(self.call('/assistant/chat', 'POST', {'text': 'Что ты знаешь обо мне?'}, owner)[0], 200)
            context = provider.call_args.args[0][1]['content']
            self.assertIn('Ремонт квартир', context)
        self.assertEqual(self.call('/assistant/memory/'+item_id, 'DELETE', token=owner)[0], 200)
        self.assertEqual(self.call('/assistant/memory', token=owner)[1]['items'], [])

    def test_model_can_remember_user_fact_and_read_it_without_confirmation(self):
        owner, _ = self.account('automatic-memory')
        prompt = 'Я занимаюсь ремонтом квартир'
        response = {'tool_calls': [{'id': 'remember-1', 'type': 'function', 'function': {
            'name': 'remember_knowledge', 'arguments': '{"title":"Специализация","content":"Ремонт квартир","evidence":"Я занимаюсь ремонтом квартир"}'}}]}
        with patch.dict(os.environ, OPENROUTER_API_KEY='test-only'), patch('backend.assistant.query_model', side_effect=[response, {'content': 'Запомнил специализацию'}]):
            status, answer = self.call('/assistant/chat', 'POST', {'text': prompt}, owner)
        self.assertEqual(status, 200, answer)
        self.assertEqual(answer['actions'], [])
        item = self.call('/assistant/memory', token=owner)[1]['items'][0]
        self.assertEqual(item['source'], 'assistant')
        self.assertEqual(item['content'], 'Ремонт квартир')
        with self.mod.db() as con:
            from backend.ai_workspace import find_knowledge
            from types import SimpleNamespace

            wid = con.execute('SELECT id FROM workspaces WHERE owner_id=?', (self.call('/me', token=owner)[1]['user']['id'],)).fetchone()['id']
            user = con.execute('SELECT * FROM users WHERE id=?', (self.call('/me', token=owner)[1]['user']['id'],)).fetchone()
            result = find_knowledge(SimpleNamespace(con=con, wid=wid, user=user), 'РЕМОНТ')
            self.assertEqual(result['items'][0]['scope'], 'personal')

    def test_automatic_memory_obeys_opt_out_and_requires_user_evidence(self):
        owner, _ = self.account('memory-disabled')
        self.call('/profile', 'PATCH', {'memory_enabled': 0}, owner)
        response = {'tool_calls': [{'id': 'm', 'type': 'function', 'function': {
            'name': 'remember_knowledge', 'arguments': '{"title":"Профессия","content":"Дизайнер","evidence":"Я дизайнер"}'}}]}
        with patch.dict(os.environ, OPENROUTER_API_KEY='test-only'), patch('backend.assistant.query_model', side_effect=[response, {'content': 'Память выключена'}]):
            self.assertEqual(self.call('/assistant/chat', 'POST', {'text': 'Я дизайнер'}, owner)[0], 200)
        self.assertEqual(self.call('/assistant/memory', token=owner)[1]['items'], [])
        self.call('/profile', 'PATCH', {'memory_enabled': 1}, owner)
        with patch.dict(os.environ, OPENROUTER_API_KEY='test-only'), patch('backend.assistant.query_model', side_effect=[response, {'content': 'Не удалось сохранить'}]):
            self.assertEqual(self.call('/assistant/chat', 'POST', {'text': 'Привет'}, owner)[0], 200)
        self.assertEqual(self.call('/assistant/memory', token=owner)[1]['items'], [])
