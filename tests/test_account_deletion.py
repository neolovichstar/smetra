"""Account deletion must preserve business records in another owner's workspace."""

import base64
import unittest

from tests import test_business


class AccountDeletion(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    account = test_business.BusinessFlows.account
    call = test_business.BusinessFlows.call

    def test_deleted_member_preserves_shared_quotes_and_attachments(self):
        owner, _ = self.account('delete-team-owner')
        member, member_id = self.account('delete-team-member')
        shared = self.call('/workspace', token=owner)[1]['workspace']['id']
        self.assertEqual(self.call('/workspace/members', 'POST',
            {'email': 'delete-team-member@test.invalid', 'role': 'member'}, owner)[0], 200)
        body = {'title': 'Shared team work', 'client': 'QA', 'amount': 10000}
        status, result = self.call('/quotes', 'POST', body, member, shared)
        self.assertEqual(status, 201, result)
        quote = result['quote']
        status, result = self.call('/files', 'POST', {'quote_id': quote['id'], 'name': 'brief.txt',
            'content': base64.b64encode(b'Shared specification').decode()}, member, shared)
        self.assertEqual(status, 201, result)
        file_id = result['file']['id']
        personal = self.call('/workspace', token=member)[1]['workspace']['id']
        personal_quote = self.call('/quotes', 'POST', body, member)[1]['quote']['id']
        self.assertEqual(self.call('/me', 'DELETE', token=member)[0], 200)
        self.assertEqual(self.call('/quotes/'+quote['id'], token=owner, workspace=shared)[0], 200)
        self.assertEqual(self.call('/files/'+file_id, token=owner, workspace=shared, raw=True)[1], b'Shared specification')
        self.assertEqual(self.call('/me', token=member)[0], 401)
        with self.mod.db() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM quotes WHERE id=?', (personal_quote,)).fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT count(*) FROM workspaces WHERE id=?', (personal,)).fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT count(*) FROM workspace_members WHERE user_id=?', (member_id,)).fetchone()[0], 0)
